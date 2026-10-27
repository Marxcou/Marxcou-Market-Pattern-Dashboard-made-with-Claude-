// Grundregel 3: every detected pattern is explained completely.
import { expect, test } from "./helpers/fixtures";
import { findForbidden } from "./helpers/grundregeln";

test.beforeEach(async ({ page, app }) => {
  await page.goto(`/instrument/${app.demo.id}`);
});

test("Doppelboden wird gelistet und mit allen Pflichtangaben erklärt", async ({ page }) => {
  const list = page.getByTestId("pattern-list");
  await expect(list.getByRole("button", { name: /Double bottom/ })).toBeVisible();
  await list.getByRole("button", { name: /Double bottom/ }).click();

  const panel = page.getByTestId("pattern-panel");
  await expect(panel).toBeVisible();
  // name, position in the chart with period, status
  await expect(panel.getByRole("heading", { name: "Double bottom" })).toBeVisible();
  await expect(panel.getByTestId("pattern-range")).toContainText(/Lage im Chart: \d{2}\.\d{2}\.\d{4} bis \d{2}\.\d{2}\.\d{4}/);
  await expect(panel.getByTestId("pattern-status")).toContainText("Bestätigt");
  // explanation in plain words: labeled as template without a key or with demo data, never presented as AI
  const ai = panel.getByTestId("ai-explanation");
  await expect(ai.getByTestId("ai-explanation-text")).toContainText("Double bottom");
  await expect(ai.getByTestId("ai-explanation-label")).toContainText("Vorlage, ohne KI");
  await expect(ai.getByTestId("ai-explanation-reason")).toContainText("Kein KI-Text");
  // met criteria with actual values
  const rows = panel.getByTestId("criteria-table").locator("tbody tr");
  expect(await rows.count()).toBeGreaterThanOrEqual(3);
  await expect(panel.getByTestId("criteria-table")).toContainText("erfüllt");
  await expect(panel.getByTestId("criteria-table").locator("tbody tr").first().locator("td").nth(2)).toContainText(/\d/);
  // Konfidenz samt Berechnung
  await expect(panel.getByTestId("confidence")).toHaveText(/\d+\s?%/);
  await expect(panel.getByTestId("confidence-table")).toContainText("Summe");
  await expect(panel.getByText("Die Konfidenz beschreibt nur, wie genau die Kerzen zur Musterdefinition passen")).toBeVisible();
  // at least two scenarios and both levels
  expect(await panel.getByTestId("scenario").count()).toBeGreaterThanOrEqual(2);
  await expect(panel.getByTestId("levels")).toContainText("Bestätigungsniveau:");
  await expect(panel.getByTestId("levels")).toContainText("Ungültigkeitsniveau:");
  // backtest with sample size (explicitly labeled as a sample value in the demo run)
  await expect(panel.getByTestId("backtest")).toContainText(/Stichprobe|Fälle/);
  await expect(panel.getByTestId("backtest")).toContainText(/120/);
  // method, parameters, data basis with source
  await panel.getByText("Verfahren, Parameter und Datenbasis").click();
  await expect(panel.getByText(/Parameter-Kennung/)).toBeVisible();
  await expect(panel.getByText("Quelle: Demo price source (sample data)")).toBeVisible();
  // Grundregel 1
  expect(findForbidden(await panel.innerText())).toBeNull();
});

test("Zeitraum ohne Tageskerzen nennt den Grund für fehlende Muster", async ({ page }) => {
  await page.getByRole("group", { name: "Zeitraum" }).getByRole("button", { name: "1T", exact: true }).click();
  await expect(page.getByTestId("no-patterns")).toContainText("Die Mustererkennung arbeitet nur mit Tages- und Stundenkerzen");
});
