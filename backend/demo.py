"""FinAlly terminal demo: check that the backend works, then watch live prices.

Run from backend/:

    uv run python demo.py              # all checks + 20s live price board
    uv run python demo.py --seconds 60 # longer live board (Ctrl+C ends it early)
    uv run python demo.py --no-live    # checks only

It always uses the built-in simulator (MASSIVE_API_KEY is ignored), needs no
network or API keys, and exits with code 1 if any check fails.
"""

import argparse
import asyncio
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
PAYLOAD_KEYS = {"price", "previous_price", "change_percent", "direction", "timestamp"}
ISO_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
SPARKS = "▁▂▃▄▅▆▇█"

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def green(text: str) -> str:
    return color(text, "32")


def red(text: str) -> str:
    return color(text, "31")


def bold(text: str) -> str:
    return color(text, "1")


def dim(text: str) -> str:
    return color(text, "2")


class Checks:
    """Runs named checks and records pass/fail. A check fails by raising."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed: list[str] = []

    def section(self, title: str) -> None:
        print(f"\n{bold(title)}")

    async def run(self, name: str, fn) -> None:
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:
            self.failed.append(name)
            print(f"  {red('FAIL')}  {name}")
            detail = str(exc) or type(exc).__name__
            print(f"        {red(detail)}")
            if not isinstance(exc, AssertionError):
                print(dim("".join(traceback.format_exception(exc)[-3:]).rstrip()))
            return
        self.passed += 1
        suffix = f"  {dim(str(result))}" if result else ""
        print(f"  {green('PASS')}  {name}{suffix}")


# ---------------------------------------------------------------- unit checks


async def unit_checks(checks: Checks) -> None:
    from app.market import (
        InvalidTickerError,
        PriceCache,
        UnknownTickerError,
        create_market_source,
        normalize_ticker,
    )
    from app.market.massive import BASE_URL, MassiveSource, parse_snapshot
    from app.market.simulator import GBMModel, SimulatorSource

    checks.section("1. Ticker validation")

    def valid_tickers():
        assert normalize_ticker(" aapl ") == "AAPL"
        assert normalize_ticker("brk.b") == "BRK.B"
        return "' aapl ' -> AAPL, 'brk.b' -> BRK.B"

    def invalid_tickers():
        for bad in ["", "1ABC", "TOOLONGTICKER", "AA-PL"]:
            try:
                normalize_ticker(bad)
            except InvalidTickerError:
                continue
            raise AssertionError(f"{bad!r} was accepted")
        return "'', '1ABC', 'TOOLONGTICKER', 'AA-PL' rejected"

    await checks.run("valid tickers are uppercased", valid_tickers)
    await checks.run("invalid tickers are rejected", invalid_tickers)

    checks.section("2. Price cache")

    def cache_semantics():
        cache = PriceCache()
        now = datetime.now(UTC)
        first = cache.update("AAPL", 190.0, now)
        assert first.price == first.previous_price == first.reference_price == 190.0
        second = cache.update("AAPL", 191.9, now)
        assert second.previous_price == 190.0 and second.reference_price == 190.0
        assert second.direction == "up", second.direction
        assert second.change_percent == 1.0, second.change_percent
        payload = second.to_dict()
        assert set(payload) == PAYLOAD_KEYS, payload
        assert ISO_RE.match(payload["timestamp"]), payload["timestamp"]
        return f"190.00 -> 191.90 = {second.direction}, {second.change_percent:+.2f}%"

    await checks.run("update, direction, change % and payload", cache_semantics)

    checks.section("3. Price simulator")

    def gbm_moves():
        model = GBMModel()
        for t in DEFAULT_TICKERS + ["PYPL"]:
            model.add(t)
        start = dict((t, s.price) for t, s in model.states.items())
        for _ in range(1000):
            prices = model.step()
        assert all(p > 0 for p in prices.values()), "a price went non-positive"
        assert prices != start, "prices did not move"
        assert 50 <= start["PYPL"] <= 300, f"unknown ticker seed {start['PYPL']}"
        return f"AAPL {start['AAPL']:.2f} -> {prices['AAPL']:.2f} after 1000 ticks"

    async def simulator_source():
        cache = PriceCache()
        source = SimulatorSource(cache, tick_seconds=0.05)
        await source.start(DEFAULT_TICKERS)
        try:
            assert set(cache.snapshot()) == set(DEFAULT_TICKERS)
            before = cache.get("AAPL").timestamp
            await asyncio.sleep(0.2)
            assert cache.get("AAPL").timestamp > before, "background loop is not ticking"
            await source.add_ticker("PYPL")
            assert "PYPL" in cache, "added ticker has no price"
            await source.remove_ticker("PYPL")
            assert "PYPL" not in cache, "removed ticker still in cache"
        finally:
            await source.stop()
        return "start, tick, add, remove, stop"

    await checks.run("GBM model keeps prices positive and moving", gbm_moves)
    await checks.run("simulator source runs in the background", simulator_source)

    checks.section("4. Massive API source (faked, no network)")

    sample = {
        "ticker": "AAPL",
        "updated": 1605192894630916600,
        "day": {"c": 190.4},
        "prevDay": {"c": 189.27},
        "lastTrade": {"p": 190.5, "t": 1605192894630916600},
    }

    def parse_sample():
        quote = parse_snapshot(sample)
        assert quote.price == 190.5 and quote.reference_price == 189.27, quote
        assert quote.timestamp.year == 2020, quote.timestamp
        return f"price {quote.price}, prev close {quote.reference_price}"

    async def massive_source():
        def handler(request: httpx.Request) -> httpx.Response:
            assert "apiKey" not in str(request.url), "API key leaked into the URL"
            wanted = request.url.params["tickers"].split(",")
            items = [dict(sample, ticker=t) for t in wanted if t == "AAPL"]
            return httpx.Response(200, json={"status": "OK", "tickers": items})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)
        cache = PriceCache()
        source = MassiveSource(cache, "demo-key", client=client)
        await source.start(["AAPL"])
        try:
            assert cache.price("AAPL") == 190.5
            try:
                await source.add_ticker("ZZZZ")
            except UnknownTickerError:
                pass
            else:
                raise AssertionError("unknown ticker was accepted")
        finally:
            await source.stop()
        return "poll fills cache, unknown ticker rejected"

    await checks.run("snapshot parsing", parse_sample)
    await checks.run("poll and add_ticker", massive_source)

    checks.section("5. Source selection")

    async def factory():
        saved = os.environ.get("MASSIVE_API_KEY")
        try:
            os.environ["MASSIVE_API_KEY"] = "  "
            assert type(create_market_source(PriceCache())).__name__ == "SimulatorSource"
            os.environ["MASSIVE_API_KEY"] = "demo-key"
            massive = create_market_source(PriceCache())
            assert type(massive).__name__ == "MassiveSource"
            await massive.stop()
        finally:
            if saved is None:
                os.environ.pop("MASSIVE_API_KEY", None)
            else:
                os.environ["MASSIVE_API_KEY"] = saved
        return "no key -> simulator, key -> Massive"

    await checks.run("MASSIVE_API_KEY picks the source", factory)


# -------------------------------------------------------------- server checks


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """The real app under uvicorn, in a child process."""

    def __init__(self) -> None:
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.log = tempfile.NamedTemporaryFile("w+", prefix="finally-demo-", suffix=".log")
        env = dict(os.environ, MASSIVE_API_KEY="")  # always the simulator
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=BACKEND_DIR,
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # Ctrl+C in the terminal must not stop it
        )

    async def wait_ready(self, timeout: float = 20) -> float:
        start = time.monotonic()
        async with httpx.AsyncClient() as client:
            while time.monotonic() - start < timeout:
                if self.proc.poll() is not None:
                    raise AssertionError(f"server exited with code {self.proc.returncode}")
                try:
                    await client.get(f"{self.base}/api/health", timeout=1)
                    return time.monotonic() - start
                except httpx.TransportError:
                    await asyncio.sleep(0.2)
        raise AssertionError(f"server not ready after {timeout:.0f}s")

    def log_tail(self, lines: int = 15) -> str:
        self.log.seek(0)
        return "".join(self.log.readlines()[-lines:])

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        self.log.close()


async def read_events(base: str, count: int) -> tuple[httpx.Headers, list[dict], list[float]]:
    """Read `count` SSE data events; return headers, payloads and arrival times."""
    events, times = [], []
    async with httpx.AsyncClient(timeout=10) as client:
        async with client.stream("GET", f"{base}/api/stream/prices") as response:
            assert response.status_code == 200, f"HTTP {response.status_code}"
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
                    times.append(time.monotonic())
                    if len(events) == count:
                        return response.headers, events, times
    raise AssertionError("stream ended early")


async def server_checks(checks: Checks, server: Server) -> bool:
    checks.section("6. Real server (uvicorn)")

    async def ready():
        return f"up in {await server.wait_ready():.1f}s on port {server.port}"

    await checks.run("server starts", ready)
    if checks.failed and checks.failed[-1] == "server starts":
        print(dim(server.log_tail()))
        return False

    async def health():
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{server.base}/api/health")
        assert r.status_code == 200 and r.json() == {"status": "ok"}, r.text
        return '{"status": "ok"}'

    stream: dict = {}

    async def sse_headers():
        headers, events, times = await read_events(server.base, 4)
        stream.update(events=events, times=times)
        assert headers["content-type"].startswith("text/event-stream"), headers["content-type"]
        assert headers.get("cache-control") == "no-cache"
        return headers["content-type"]

    def sse_tickers():
        tickers = sorted(stream["events"][-1])
        assert tickers == sorted(DEFAULT_TICKERS), tickers
        return f"{len(tickers)} default tickers"

    def sse_payload():
        for entry in stream["events"][-1].values():
            assert set(entry) == PAYLOAD_KEYS, entry
            assert entry["price"] > 0
            assert entry["direction"] in {"up", "down", "flat"}
            assert ISO_RE.match(entry["timestamp"]), entry["timestamp"]
        aapl = stream["events"][-1]["AAPL"]
        return f"AAPL {aapl['price']} {aapl['direction']} {aapl['change_percent']:+.2f}%"

    def sse_timing():
        times = stream["times"]
        gaps = [b - a for a, b in zip(times, times[1:])]
        avg = sum(gaps) / len(gaps)
        assert 0.3 <= avg <= 0.8, f"average gap {avg:.2f}s, expected ~0.5s"
        first, last = stream["events"][0], stream["events"][-1]
        moved = [t for t in last if last[t]["timestamp"] != first[t]["timestamp"]]
        assert moved, "no ticker updated between events"
        return f"one event every {avg:.2f}s, {len(moved)} tickers updated"

    await checks.run("GET /api/health", health)
    await checks.run("GET /api/stream/prices is an SSE stream", sse_headers)
    if "events" in stream:
        await checks.run("stream contains the watchlist", sse_tickers)
        await checks.run("payload matches the spec", sse_payload)
        await checks.run("updates arrive every ~500ms", sse_timing)
    return True


async def shutdown_check(checks: Checks, server: Server) -> None:
    checks.section("8. Clean shutdown")

    async def stop_with_open_client():
        async with httpx.AsyncClient(timeout=10) as client:
            async with client.stream("GET", f"{server.base}/api/stream/prices") as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        break
                start = time.monotonic()
                server.proc.send_signal(signal.SIGTERM)
                while server.proc.poll() is None:
                    if time.monotonic() - start > 5:
                        raise AssertionError("server still running 5s after SIGTERM")
                    await asyncio.sleep(0.05)
        return f"exited in {time.monotonic() - start:.2f}s with a browser tab open"

    await checks.run("SIGTERM stops the server while a client is connected", stop_with_open_client)


# ----------------------------------------------------------------- live board


def sparkline(values) -> str:
    lo, hi = min(values), max(values)
    if hi == lo:
        return SPARKS[3] * len(values)
    return "".join(SPARKS[round((v - lo) / (hi - lo) * (len(SPARKS) - 1))] for v in values)


def render(snapshot: dict, history: dict, remaining: float) -> str:
    lines = [
        bold("FinAlly live prices") + dim(f"   (simulator, {remaining:4.1f}s left, Ctrl+C to stop)"),
        "",
        bold(f"  {'TICKER':<7}{'PRICE':>10}{'CHANGE':>10}   TREND"),
    ]
    for ticker, e in snapshot.items():
        arrow, paint = {"up": ("▲", green), "down": ("▼", red)}.get(e["direction"], ("•", dim))
        change = f"{e['change_percent']:+.2f}%"
        change = green(f"{change:>10}") if e["change_percent"] >= 0 else red(f"{change:>10}")
        price = paint(f"{e['price']:>10.2f}")
        lines.append(f"  {ticker:<7}{price}{change}   {paint(arrow)} {sparkline(history[ticker])}")
    return "\n".join(lines)


async def live_board(base: str, seconds: float) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, stop.set)
    history: dict[str, deque] = defaultdict(lambda: deque(maxlen=40))
    last_ts: dict[str, str] = {}
    end = time.monotonic() + seconds
    frame = ""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            async with client.stream("GET", f"{base}/api/stream/prices") as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    snapshot = json.loads(line[6:])
                    for ticker, entry in snapshot.items():
                        if last_ts.get(ticker) != entry["timestamp"]:
                            last_ts[ticker] = entry["timestamp"]
                            history[ticker].append(entry["price"])
                    remaining = max(0.0, end - time.monotonic())
                    frame = render(snapshot, history, remaining)
                    if USE_COLOR:
                        print("\033[H\033[J" + frame, flush=True)
                    if stop.is_set() or remaining == 0:
                        break
    finally:
        loop.remove_signal_handler(signal.SIGINT)
    if not USE_COLOR:
        print(frame)  # no terminal: print only the final frame


# ----------------------------------------------------------------------- main


async def main(args: argparse.Namespace) -> int:
    print(bold("FinAlly backend demo"))
    checks = Checks()
    await unit_checks(checks)

    server = Server()
    try:
        if await server_checks(checks, server):
            if not args.no_live and server.proc.poll() is None:
                checks.section("7. Live price board")
                print(dim(f"  showing live prices for {args.seconds:.0f}s..."))
                await asyncio.sleep(1)
                try:
                    await live_board(server.base, args.seconds)
                    print()
                    print(f"  {green('DONE')}  live board")
                except Exception as exc:
                    checks.failed.append("live board")
                    print(f"  {red('FAIL')}  live board: {exc}")
            await shutdown_check(checks, server)
    finally:
        server.kill()

    total = checks.passed + len(checks.failed)
    print()
    if checks.failed:
        print(red(bold(f"{len(checks.failed)} of {total} checks failed:")))
        for name in checks.failed:
            print(red(f"  - {name}"))
        return 1
    print(green(bold(f"All {total} checks passed. The market data backend is working.")))
    print(dim("Not built yet, so not checked: database, portfolio/watchlist/chat API, "
              "AI assistant, frontend, Docker."))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=20, help="live board duration")
    parser.add_argument("--no-live", action="store_true", help="skip the live price board")
    sys.exit(asyncio.run(main(parser.parse_args())))
