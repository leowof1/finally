import { test, expect, Page } from "@playwright/test";

const STREAM = "**/api/stream/prices";

/**
 * Track every EventSource the app creates, so a test can cut a live stream.
 * Needed because context.setOffline() and page.route() do not affect an
 * already-open EventSource in Chromium (verified: messages keep flowing).
 */
async function trackEventSources(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __sources: EventSource[] };
    w.__sources = [];
    const Native = window.EventSource;
    window.EventSource = class extends Native {
      constructor(url: string | URL, init?: EventSourceInit) {
        super(url, init);
        w.__sources.push(this);
      }
    };
  });
}

/** Close all live streams and fire error, as Chromium does when it gives up on a stream. */
async function dropStreams(page: Page) {
  await page.evaluate(() => {
    const w = window as unknown as { __sources: EventSource[] };
    for (const s of w.__sources) {
      if (s.readyState !== EventSource.CLOSED) {
        s.close();
        s.dispatchEvent(new Event("error"));
      }
    }
  });
}

async function expectPricesMoving(page: Page) {
  const price = page.getByTestId("price-AAPL");
  await expect(price).toHaveText(/\d+\.\d{2}/);
  const first = await price.innerText();
  await expect(price).not.toHaveText(first);
}

test("connection status recovers after the first stream connection fails", async ({ page }) => {
  await page.route(STREAM, (route) => route.abort());
  await page.goto("/");

  const status = page.getByTestId("connection-status");
  await expect(status).not.toHaveAttribute("data-status", "connected");

  await page.unroute(STREAM);
  await expect(status).toHaveAttribute("data-status", "connected", { timeout: 20_000 });
  await expectPricesMoving(page);
});

test("connection status recovers after a live stream drops", async ({ page }) => {
  await trackEventSources(page);
  await page.goto("/");

  const status = page.getByTestId("connection-status");
  await expect(status).toHaveAttribute("data-status", "connected");
  await expectPricesMoving(page);

  await page.route(STREAM, (route) => route.abort());
  await dropStreams(page);
  await expect(status).not.toHaveAttribute("data-status", "connected");

  await page.unroute(STREAM);
  await expect(status).toHaveAttribute("data-status", "connected", { timeout: 20_000 });
  await expectPricesMoving(page);
});
