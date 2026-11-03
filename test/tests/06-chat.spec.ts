import { test, expect } from "@playwright/test";
import { heldQuantity, waitForPrice } from "./helpers";

test("mocked AI chat buys AAPL and shows the trade inline", async ({ page, request }) => {
  await waitForPrice(request, "AAPL");
  const before = await heldQuantity(request, "AAPL");

  await page.goto("/");
  await page.getByTestId("chat-input").fill("buy AAPL");
  await page.getByTestId("chat-send").click();

  await expect(page.locator('[data-testid="chat-message"][data-role="user"]').last()).toContainText("buy AAPL");
  const reply = page.locator('[data-testid="chat-message"][data-role="assistant"]').last();
  await expect(reply).toContainText("Mock: bought 1 AAPL");
  await expect(reply.getByTestId("chat-trade")).toContainText("Bought 1 AAPL");
  await expect(page.getByTestId("chat-loading")).toHaveCount(0);

  await expect(page.getByTestId("position-row-AAPL")).toBeVisible();
  expect(await heldQuantity(request, "AAPL")).toBe(before + 1);
});
