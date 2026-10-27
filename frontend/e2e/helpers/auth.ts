// The only place for logging in within the E2E tests. If the login changes, only this file needs to be adapted.
// Accounts with a one-time password (must_change_password) must set their own password before use;
// both helpers do that when `newPassword` is given and otherwise fail with a clear message.
import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_ADMIN } from "./credentials.mjs";

export interface Credentials { email: string; password: string }
export const CREDENTIALS: Credentials = E2E_ADMIN;

/** Login through the interface (for the tests of the login flow itself). */
export async function loginViaUi(page: Page, creds: Credentials = CREDENTIALS, opts: { newPassword?: string } = {}): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("E-Mail").fill(creds.email);
  await page.getByLabel("Passwort").fill(creds.password);
  await page.getByRole("button", { name: "Anmelden" }).click();
  if (opts.newPassword) await changeForcedPasswordViaUi(page, creds.password, opts.newPassword);
  await expect(page.getByRole("heading", { name: "Watchlist" })).toBeVisible();
}

/** Mandatory password change after a one-time password (page "Change password"). */
export async function changeForcedPasswordViaUi(page: Page, current: string, next: string): Promise<void> {
  await expect(page.getByTestId("forced-change")).toBeVisible();
  await page.getByLabel("Aktuelles Passwort").fill(current);
  await page.getByLabel("Neues Passwort (mindestens 10 Zeichen)").fill(next);
  await page.getByLabel("Neues Passwort wiederholen").fill(next);
  await page.getByRole("button", { name: "Passwort ändern" }).click();
  // After the change the interface unlocks the pages (no detour via the account page needed)
}

/** Login via the API; the session cookies then apply to the page and requests of the same context. Returns the CSRF token. */
export async function loginViaApi(request: APIRequestContext, creds: Credentials = CREDENTIALS, opts: { newPassword?: string } = {}): Promise<string> {
  const res = await request.post("/api/auth/login", { data: creds });
  expect(res.ok(), `API-Login fehlgeschlagen: ${res.status()}`).toBeTruthy();
  const me = (await res.json()) as { csrf_token: string; user: { must_change_password?: boolean } };
  if (me.user.must_change_password) {
    expect(opts.newPassword, `${creds.email} hat ein Einmalpasswort: newPassword angeben`).toBeTruthy();
    const r = await request.post("/api/auth/change-password", {
      data: { current_password: creds.password, new_password: opts.newPassword },
      headers: { "X-CSRF-Token": me.csrf_token },
    });
    expect(r.ok(), `Passwortwechsel fehlgeschlagen: ${r.status()}`).toBeTruthy();
  }
  return me.csrf_token;
}
