// Grundregeln 1, 5 and 6 on every page of the interface.
import { expect, test } from "./helpers/fixtures";
import { DISCLAIMER, DISCLAIMER_DE, findForbidden } from "./helpers/grundregeln";

const STATIC_PAGES = ["/", "/nachrichten", "/quellen", "/gibt-es-nicht"];

test("Hinweis, Demo-Banner und neutrale Sprache auf jeder Seite", async ({ page, app }) => {
  for (const path of [...STATIC_PAGES, `/instrument/${app.demo.id}`]) {
    await page.goto(path);
    await expect(page.getByTestId("disclaimer").first(), path).toHaveText(DISCLAIMER_DE);
    await expect(page.getByTestId("disclaimer").first(), path).toBeVisible();
    // Grundregel 6: invented data only with a visible label
    await expect(page.getByTestId("demo-banner"), path).toContainText("DEMO-MODUS");
    if (path.startsWith("/instrument/")) await expect(page.getByTestId("price-chart")).toBeVisible();
    else await page.waitForLoadState("networkidle");
    // Grundregel 1: no recommendation language in the visible text
    const text = await page.locator("body").innerText();
    expect(findForbidden(text), `verbotener Begriff auf ${path}`).toBeNull();
  }
});

test("Disclaimer-Text im Frontend entspricht dem Wortlaut der Grundregel", async () => {
  expect(DISCLAIMER).toBe("This dashboard does not constitute investment advice. All analyses are automated, may be incorrect and are for information only.");
  expect(DISCLAIMER_DE).toContain("keine Anlageberatung");
});
