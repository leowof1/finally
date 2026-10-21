# Massive API Reference (formerly Polygon.io)

Reference for the parts of the Massive REST API that FinAlly uses: live prices for several tickers at once, and end-of-day prices. Researched October 2026 from the official docs (`https://massive.com/docs`, add `.md` to any page URL to get Markdown) and the official Python client source (`github.com/massive-com/client-python`).

## 1. Background

- Polygon.io was renamed Massive.com on 30 Oct 2025. Existing keys still work.
- REST base URL: `https://api.massive.com` (the old `api.polygon.io` host still works but don't use it in new code).
- Official Python package: `massive` (PyPI, version 2.9.0, Python >= 3.10). It replaces `polygon-api-client`.
- The full index of documentation pages is at `https://massive.com/docs/llms.txt`.

## 2. Authentication

You can pass the API key in either of two ways:

```bash
# Query string
curl "https://api.massive.com/v2/aggs/ticker/AAPL/prev?apiKey=$MASSIVE_API_KEY"

# Header (preferred: keeps the key out of URLs and logs)
curl -H "Authorization: Bearer $MASSIVE_API_KEY" \
  "https://api.massive.com/v2/aggs/ticker/AAPL/prev"
```

The Python client reads `MASSIVE_API_KEY` from the environment when no `api_key` is passed. That is the same variable name FinAlly uses.

```python
from massive import RESTClient

client = RESTClient()                    # uses os.environ["MASSIVE_API_KEY"]
client = RESTClient(api_key="...")       # or pass it explicitly
```

The client is **synchronous** (urllib3 under the hood) and retries failed requests by itself. In an asyncio app, call it with `asyncio.to_thread(...)`.

## 3. Plans, Rate Limits and Data Freshness

| Plan | Price | Rate limit | Snapshot endpoints | Data freshness |
|---|---|---|---|---|
| Stocks Basic | free | 5 calls/min | **Not included** | End of day |
| Stocks Starter | paid | unlimited | Included | 15-minute delayed |
| Stocks Developer | paid | unlimited | Included | 15-minute delayed |
| Stocks Advanced | paid | unlimited | Included | Real-time |
| Stocks Business | paid | unlimited | Included | Real-time |

Going over the rate limit returns HTTP `429`. If your plan doesn't include an endpoint, the request fails with an authorization error.

**Impact on FinAlly:** the multi-ticker snapshot described in PLAN.md needs **Starter or higher**. A free Basic key can only call the end-of-day endpoints (Section 6). See MARKET_INTERFACE.md, "Plan requirements", for how the backend deals with this.

## 4. Multi-Ticker Snapshot (the live endpoint FinAlly uses)

```
GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT,TSLA
```

| Query param | Type | Notes |
|---|---|---|
| `tickers` | comma-separated string | Case-sensitive. If empty, returns **every** ticker (10,000+), so always pass it |
| `include_otc` | bool | Default `false` |

One request returns all requested tickers. Snapshot data is cleared at 3:30 AM ET and fills in again as exchanges report, starting as early as 4:00 AM ET. Overnight, `day` can be empty while `prevDay` still has data.

### Response

```json
{
  "status": "OK",
  "count": 1,
  "tickers": [
    {
      "ticker": "AAPL",
      "todaysChange": 1.23,
      "todaysChangePerc": 0.65,
      "updated": 1605192894630916600,
      "day":     {"o": 189.1, "h": 191.0, "l": 188.7, "c": 190.5, "v": 41234567, "vw": 190.02},
      "prevDay": {"o": 188.0, "h": 189.9, "l": 187.5, "c": 189.27, "v": 52345678, "vw": 188.9},
      "min":     {"o": 190.4, "h": 190.6, "l": 190.3, "c": 190.5, "v": 120345, "t": 1684428600000},
      "lastTrade": {"p": 190.5, "s": 100, "t": 1605192894630916600, "x": 4},
      "lastQuote": {"p": 190.49, "s": 3, "P": 190.51, "S": 5, "t": 1605192959994246100}
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `lastTrade.p` | Last trade price. Only returned if your plan includes trades |
| `day.c` | Close of the current day bar so far (fallback price) |
| `prevDay.c` | Previous day's close. FinAlly uses it as `reference_price` |
| `todaysChangePerc` | % change vs previous close |
| `updated` | Last update time, **nanoseconds** since the epoch |
| `lastTrade.t`, `lastQuote.t` | Nanoseconds since the epoch |
| `min.t` | **Milliseconds** since the epoch (bar start) |

### Python

```python
from massive import RESTClient

client = RESTClient()
snapshots = client.get_snapshot_all("stocks", tickers=["AAPL", "MSFT", "TSLA"])

for s in snapshots:  # list[TickerSnapshot]
    price = s.last_trade.price if s.last_trade else s.day.close
    print(s.ticker, price, s.prev_day.close, s.todays_change_percent, s.updated)
```

`TickerSnapshot` attributes (snake_case versions of the JSON keys): `ticker`, `day`, `prev_day`, `min`, `last_trade`, `last_quote`, `todays_change`, `todays_change_percent`, `updated`. `day` / `prev_day` are `Agg` objects (`open`, `high`, `low`, `close`, `volume`, `vwap`). `last_trade` is a `LastTrade` (`price`, `size`, `sip_timestamp`, ...).

### Raw HTTP (no SDK)

```python
import httpx

def fetch_snapshot(api_key: str, tickers: list[str]) -> dict:
    """Fetch the snapshot for several tickers in a single request."""
    r = httpx.get(
        "https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers",
        params={"tickers": ",".join(tickers)},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()
```

## 5. Single-Ticker Snapshot

```
GET /v2/snapshot/locale/us/markets/stocks/tickers/{stocksTicker}
```

The response is the same object as one entry of Section 4, under the key `ticker`. Python: `client.get_snapshot_ticker("stocks", "AAPL")`. Plan access is the same (Starter and up). For an unknown symbol the request fails. You can also call the multi-ticker endpoint with a single ticker and check whether the result is empty. FinAlly does that when validating a new watchlist ticker.

## 6. End-of-Day Prices (works on the free plan)

### 6.1 Previous Day Bar: one ticker

```
GET /v2/aggs/ticker/{stocksTicker}/prev?adjusted=true
```

```json
{
  "ticker": "AAPL", "status": "OK", "resultsCount": 1, "adjusted": true,
  "results": [{"T": "AAPL", "o": 115.55, "h": 117.59, "l": 114.13, "c": 115.97,
               "v": 131704427, "vw": 116.3058, "t": 1605042000000}]
}
```

```python
bars = client.get_previous_close_agg("AAPL")   # list[PreviousCloseAgg]
print(bars[0].close)
```

### 6.2 Daily Market Summary (grouped daily): all tickers, one date, one call

```
GET /v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=true
```

This endpoint returns OHLC bars for **every** US stock on one trading date. It is the cheapest way to get end-of-day prices for many tickers: one call no matter how many tickers you need. Filter the results on the client side.

```json
{
  "status": "OK", "resultsCount": 10938, "adjusted": true,
  "results": [{"T": "AAPL", "o": 189.1, "h": 191.0, "l": 188.7, "c": 190.5,
               "v": 41234567, "vw": 190.02, "n": 512345, "t": 1697227200000}]
}
```

```python
wanted = {"AAPL", "MSFT", "TSLA"}
bars = client.get_grouped_daily_aggs("2026-10-20")    # list[GroupedDailyAgg]
closes = {b.ticker: b.close for b in bars if b.ticker in wanted}
```

On a weekend or holiday the request succeeds but `results` is empty. Step back day by day until you get data.

### 6.3 Daily Ticker Summary: one ticker, one date, with pre/after market

```
GET /v1/open-close/{stocksTicker}/{date}
```

```python
d = client.get_daily_open_close_agg("AAPL", "2026-10-20")
print(d.open, d.close, d.pre_market, d.after_hours)
```

### 6.4 Custom Bars: history for one ticker

```
GET /v2/aggs/ticker/{stocksTicker}/range/{multiplier}/{timespan}/{from}/{to}
```

```python
for bar in client.list_aggs("AAPL", 1, "day", "2026-09-01", "2026-10-20", limit=50000):
    print(bar.timestamp, bar.close)   # list_aggs paginates automatically
```

FinAlly doesn't need history (charts are built from the SSE stream), but this is the endpoint to use if that changes.

## 7. Other Endpoints (not used)

| Endpoint | Python | Why not |
|---|---|---|
| `GET /v2/last/trade/{ticker}` | `get_last_trade` | One ticker per call. Developer plan and up |
| `GET /v2/last/nbbo/{ticker}` | `get_last_quote` | One ticker per call. Advanced plan and up |
| `GET /v3/snapshot?ticker.any_of=...` | `list_universal_snapshots` | Unified multi-asset snapshot (max 250 tickers, paginated). More than we need |
| WebSocket `wss://socket.massive.com/stocks` | `WebSocketClient` | PLAN.md picks REST polling for simplicity |

## 8. Errors

| Situation | Result |
|---|---|
| Missing or invalid key | HTTP 401, `{"status": "ERROR", "error": "..."}` |
| Endpoint not in plan | HTTP 403 `NOT_AUTHORIZED` |
| Rate limit exceeded | HTTP 429 |
| Unknown ticker in multi-snapshot | The ticker is missing from `tickers` (no error) |

The Python client raises `massive.exceptions.BadResponse` for responses other than 2xx. If a poll fails, FinAlly logs it and tries again on the next poll; it does not crash the background task.

## 9. Sources

- REST quickstart (auth): https://massive.com/docs/rest/quickstart.md
- Full market snapshot: https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot.md
- Single ticker snapshot: https://massive.com/docs/rest/stocks/snapshots/single-ticker-snapshot.md
- Previous day bar: https://massive.com/docs/rest/stocks/aggregates/previous-day-bar.md
- Daily market summary: https://massive.com/docs/rest/stocks/aggregates/daily-market-summary.md
- Python client: https://github.com/massive-com/client-python (`massive/rest/snapshot.py`, `massive/rest/aggs.py`)
