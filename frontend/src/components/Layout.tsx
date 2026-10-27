import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { api, type Meta } from "../lib/api";
import { useAuth } from "../lib/auth";
import { LanguageSwitch, useI18n, type MessageKey } from "../lib/i18n";

// Der Hinweis kommt aus dem Wörterbuch der gewählten Sprache und ist damit auch ohne /api/meta sichtbar (Grundregel 5).
export function Disclaimer() {
  const { t } = useI18n();
  return (
    <div role="note" data-testid="disclaimer" className="border-y border-amber-700/40 bg-amber-950/40 px-4 py-2 text-xs text-amber-200 sm:text-sm">
      {t("disclaimer")}
    </div>
  );
}

// Schlichte, neutrale Symbole (keine Kauf-/Verkaufsanmutung): Umrisse ohne Farbe und ohne Pfeile.
const icon = (d: string) => (
  <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
);
const ICONS = {
  watchlist: icon("M4 5h16M4 12h16M4 19h10"),
  news: icon("M5 4h11a2 2 0 0 1 2 2v13H7a2 2 0 0 1-2-2V4zM18 9h2v8a2 2 0 0 1-2 2M8 8h6M8 12h6M8 16h4"),
  sources: icon("M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"),
  account: icon("M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0"),
  admin: icon("M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20a6 6 0 0 1 12 0M17 8a2.5 2.5 0 1 1 0 5M17 20a5 5 0 0 0-2-4"),
};

interface NavItem { to: string; labelKey: MessageKey; icon: ReactNode; end?: boolean; extraMatch?: string }

function useNavItems(): NavItem[] {
  const { me } = useAuth();
  const items: NavItem[] = [
    { to: "/", labelKey: "nav.watchlist", icon: ICONS.watchlist, end: true, extraMatch: "/instrument" },
    { to: "/nachrichten", labelKey: "nav.news", icon: ICONS.news },
    { to: "/quellen", labelKey: "nav.sources", icon: ICONS.sources },
  ];
  if (me?.user.role === "admin") items.push({ to: "/admin/benutzer", labelKey: "nav.users", icon: ICONS.admin });
  items.push({ to: "/konto", labelKey: "nav.account", icon: ICONS.account });
  return items;
}

function useMatch(item: NavItem) {
  const { pathname } = useLocation();
  return (isActive: boolean) => isActive || (item.extraMatch != null && pathname.startsWith(item.extraMatch));
}

function DesktopLink({ item }: { item: NavItem }) {
  const { t } = useI18n();
  const active = useMatch(item);
  return (
    <NavLink to={item.to} end={item.end}>
      {({ isActive }) => {
        const on = active(isActive);
        return <span aria-current={on ? "page" : undefined} className={`rounded-lg px-3 py-2 text-sm ${on ? "bg-slate-800 font-semibold text-white" : "text-slate-300 hover:bg-slate-900 hover:text-white"}`}>{t(item.labelKey)}</span>;
      }}
    </NavLink>
  );
}

function TabLink({ item }: { item: NavItem }) {
  const { t } = useI18n();
  const active = useMatch(item);
  return (
    <NavLink to={item.to} end={item.end} className="flex-1">
      {({ isActive }) => {
        const on = active(isActive);
        return (
          <span aria-current={on ? "page" : undefined} className={`flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-[11px] ${on ? "text-sky-300" : "text-slate-400"}`}>
            {item.icon}{t(item.labelKey)}
          </span>
        );
      }}
    </NavLink>
  );
}

export function Layout() {
  const { me, logout } = useAuth();
  const { t } = useI18n();
  const items = useNavItems();
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: () => api<Meta>("/meta"), retry: false });
  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      {meta?.demo_mode && (
        <div role="alert" data-testid="demo-banner" className="bg-fuchsia-800 px-4 py-1.5 text-center text-xs font-semibold sm:text-sm">
          {t("demo.banner")}
        </div>
      )}
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-2">
          <Link to="/" className="shrink-0 font-semibold">{t("app.name")}<span className="hidden sm:inline">{t("app.suffix")}</span></Link>
          {me && <nav aria-label={t("nav.main")} className="ml-2 hidden gap-1 md:flex">{items.filter((i) => i.to !== "/konto").map((i) => <DesktopLink key={i.to} item={i} />)}</nav>}
          {me && (
            <div className="ml-auto flex items-center gap-2 text-sm text-slate-300">
              <LanguageSwitch />
              <NavLink to="/konto" className="hidden max-w-[10rem] truncate rounded-lg px-2 py-2 underline-offset-2 hover:underline md:block">{me.user.display_name}</NavLink>
              <button type="button" onClick={() => void logout()} className="rounded-lg px-3 py-2 hover:bg-slate-900">{t("auth.logout")}</button>
            </div>
          )}
        </div>
      </header>
      <Disclaimer />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-5"><Outlet /></main>
      <div className={me ? "pb-16 md:pb-0" : ""}><Disclaimer /></div>
      {me && (
        <nav aria-label={t("nav.mobile")} className="fixed inset-x-0 bottom-0 z-30 flex border-t border-slate-800 bg-slate-950/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
          {items.map((i) => <TabLink key={i.to} item={i} />)}
        </nav>
      )}
    </div>
  );
}
