import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Lang = "en" | "de";
export const LANGS: Lang[] = ["en", "de"];
// Wird in PR 2 auf "en" gestellt, sobald alle Seiten übersetzt sind.
export const DEFAULT_LANG: Lang = "de";
const STORAGE_KEY = "lang";

type Dict = Record<string, string>;

const en: Dict = {
  "disclaimer": "This dashboard does not constitute investment advice. All analyses are automated, may be incorrect and are for information only.",
  "nav.main": "Main navigation",
  "nav.mobile": "Main navigation (mobile)",
  "nav.watchlist": "Watchlist",
  "nav.news": "News",
  "nav.sources": "Sources",
  "nav.users": "Users",
  "nav.account": "Account",
  "app.name": "Market Pattern",
  "app.suffix": "Dashboard",
  "demo.banner": "DEMO MODE: sample data, no real market data",
  "auth.logout": "Log out",
  "lang.label": "Language",
  "lang.en": "English",
  "lang.de": "Deutsch",
};

const de: Dict = {
  "disclaimer": "Dieses Dashboard stellt keine Anlageberatung dar. Alle Analysen sind automatisiert, können fehlerhaft sein und dienen ausschließlich der Information.",
  "nav.main": "Hauptnavigation",
  "nav.mobile": "Hauptnavigation (Handy)",
  "nav.watchlist": "Watchlist",
  "nav.news": "Nachrichten",
  "nav.sources": "Quellen",
  "nav.users": "Benutzer",
  "nav.account": "Konto",
  "app.name": "Marktmuster",
  "app.suffix": "-Dashboard",
  "demo.banner": "DEMO-MODUS: Beispieldaten, keine echten Marktdaten",
  "auth.logout": "Abmelden",
  "lang.label": "Sprache",
  "lang.en": "English",
  "lang.de": "Deutsch",
};

export const DICTS: Record<Lang, Dict> = { en, de };

function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "de") return stored;
  } catch { /* localStorage nicht verfügbar */ }
  return DEFAULT_LANG;
}

export type TFn = (key: string, vars?: Record<string, string | number>) => string;

interface I18n { lang: Lang; setLang: (l: Lang) => void; t: TFn; locale: string }
const Ctx = createContext<I18n | null>(null);

export function LanguageProvider({ children, lang: forced }: { children: ReactNode; lang?: Lang }) {
  const [lang, setLangState] = useState<Lang>(forced ?? initialLang());
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { localStorage.setItem(STORAGE_KEY, l); } catch { /* ignorieren */ }
  }, []);
  const value = useMemo<I18n>(() => ({
    lang, setLang, locale: lang === "de" ? "de-DE" : "en-US",
    // Fehlt ein Schlüssel in der Sprache, fällt t() auf Englisch und zuletzt auf den Schlüssel zurück (sichtbar statt leer).
    t: (key, vars) => {
      let s = DICTS[lang][key] ?? en[key] ?? key;
      for (const [k, v] of Object.entries(vars ?? {})) s = s.replaceAll(`{${k}}`, String(v));
      return s;
    },
  }), [lang, setLang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const v = useContext(Ctx);
  if (!v) throw new Error("useI18n braucht einen LanguageProvider");
  return v;
}

export function LanguageSwitch() {
  const { lang, setLang, t } = useI18n();
  return (
    <div role="group" aria-label={t("lang.label")} className="flex text-xs">
      {LANGS.map((l) => (
        <button key={l} type="button" lang={l} aria-pressed={lang === l} onClick={() => setLang(l)}
          className={`px-2 py-1.5 ${lang === l ? "font-semibold text-white" : "text-slate-400 hover:text-white"}`}>{l.toUpperCase()}</button>
      ))}
    </div>
  );
}
