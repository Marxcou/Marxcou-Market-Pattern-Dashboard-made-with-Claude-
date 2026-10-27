import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { MESSAGES, type Lang, type MessageKey } from "./messages";

export type { Lang, MessageKey };
export const LANGS: Lang[] = ["en", "de"];
export const DEFAULT_LANG: Lang = "en";
const STORAGE_KEY = "lang";

export const DICTS: Record<Lang, Record<string, string>> = {
  en: Object.fromEntries(Object.entries(MESSAGES).map(([k, v]) => [k, v[0]])),
  de: Object.fromEntries(Object.entries(MESSAGES).map(([k, v]) => [k, v[1]])),
};

function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "de") return stored;
  } catch { /* localStorage nicht verfügbar */ }
  return DEFAULT_LANG;
}

// Aktuelle Sprache auch außerhalb von React (Formatierer, API-Schicht, Bibliotheksfunktionen).
let currentLang: Lang = DEFAULT_LANG;
export const getLang = () => currentLang;
export const getLocale = () => (currentLang === "de" ? "de-DE" : "en-US");

export type TFn = (key: MessageKey, vars?: Record<string, string | number>) => string;

// Fehlt ein Schlüssel in der Sprache, fällt tr() auf Englisch und zuletzt auf den Schlüssel zurück (sichtbar statt leer).
export function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  let s = DICTS[lang][key] ?? DICTS.en[key] ?? key;
  for (const [k, v] of Object.entries(vars ?? {})) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}
export const tr: TFn = (key, vars) => translate(currentLang, key, vars);

interface I18n { lang: Lang; setLang: (l: Lang) => void; t: TFn; locale: string }
const Ctx = createContext<I18n | null>(null);

export function LanguageProvider({ children, lang: forced }: { children: ReactNode; lang?: Lang }) {
  const [lang, setLangState] = useState<Lang>(forced ?? initialLang());
  currentLang = lang;
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = useCallback((l: Lang) => {
    currentLang = l;
    setLangState(l);
    try { localStorage.setItem(STORAGE_KEY, l); } catch { /* ignorieren */ }
  }, []);
  const value = useMemo<I18n>(() => ({
    lang, setLang, locale: lang === "de" ? "de-DE" : "en-US",
    t: (key, vars) => translate(lang, key, vars),
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
  const qc = useQueryClient();
  // Das Backend liefert Texte in der angefragten Sprache (Accept-Language): alle geladenen Daten neu abrufen.
  const choose = (l: Lang) => { if (l === lang) return; setLang(l); void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" }); };
  return (
    <div role="group" aria-label={t("lang.label")} className="flex text-xs">
      {LANGS.map((l) => (
        <button key={l} type="button" lang={l} aria-pressed={lang === l} onClick={() => choose(l)}
          className={`px-2 py-1.5 ${lang === l ? "font-semibold text-white" : "text-slate-400 hover:text-white"}`}>{l.toUpperCase()}</button>
      ))}
    </div>
  );
}
