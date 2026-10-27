import { expect, test } from "./helpers/fixtures";

test.beforeEach(async ({ page }) => {
  await page.goto("/nachrichten");
});

test("Meldungen sind zusammengeführt und nennen alle Quellen mit Link, Zeitpunkt und Stimmungsbegründung", async ({ page }) => {
  const clusters = page.getByTestId("news-cluster");
  await expect(clusters).toHaveCount(2);
  const first = clusters.filter({ hasText: "third-quarter" });
  await expect(first).toContainText("2 Quellen");
  const items = first.getByTestId("news-item");
  await expect(items).toHaveCount(2);
  await expect(items.first().getByRole("link").first()).toHaveAttribute("href", /^https:\/\/example\.org\/demo\//);
  await expect(first).toContainText("Demo news source A (sample data)");
  await expect(first).toContainText("Demo news source B (sample data)");
  await expect(first).toContainText("veröffentlicht");
  // Stimmung mit Begründung, Zitat und Methode/Modell
  await first.getByTestId("sentiment").locator("summary").click();
  await expect(first.getByTestId("sentiment")).toContainText("Methode: Wörterbuch (Demo lexicon (sample data)");
  await expect(first.getByTestId("sentiment")).toContainText("third-quarter figures");
  // Herkunft je Meldung
  await items.first().getByText(/^Quelle:/).click();
  await expect(items.first().getByText("Abgerufen:")).toBeVisible();
});

test("Filter nach Stimmung, Quelle und Aktie", async ({ page }) => {
  const clusters = page.getByTestId("news-cluster");
  await page.getByLabel("Stimmung").selectOption("positiv");
  await expect(clusters).toHaveCount(1);
  await page.getByLabel("Stimmung").selectOption("negativ");
  await expect(page.getByTestId("no-news")).toContainText("Keine Nachrichten für diese Auswahl.");
  await page.getByLabel("Stimmung").selectOption("");
  await expect(clusters).toHaveCount(2);
  await page.getByLabel("Quelle").selectOption({ label: "Demo news source A (sample data)" });
  await expect(clusters).toHaveCount(2);
  await page.getByLabel("Aktie").selectOption({ label: "DEMOA" });
  await expect(clusters).toHaveCount(2);
});

test("Stimmungsverfahren wird offen genannt", async ({ page }) => {
  await expect(page.getByTestId("sentiment-status")).toContainText("Stimmungsanalyse:");
});
