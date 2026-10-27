import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { DICTS, LanguageProvider, LanguageSwitch, useI18n } from "./i18n";

function Probe() { const { t } = useI18n(); return <p>{t("nav.news")}</p>; }

describe("i18n", () => {
  it("hat in beiden Sprachen dieselben Schlüssel", () => {
    expect(Object.keys(DICTS.de).sort()).toEqual(Object.keys(DICTS.en).sort());
  });
  it("hat den Hinweis (Grundregel 5) in beiden Sprachen", () => {
    expect(DICTS.en.disclaimer).toContain("does not constitute investment advice");
    expect(DICTS.de.disclaimer).toContain("keine Anlageberatung");
  });
  it("wechselt die Sprache und merkt sie sich", () => {
    localStorage.clear();
    render(<QueryClientProvider client={new QueryClient()}><LanguageProvider><LanguageSwitch /><Probe /></LanguageProvider></QueryClientProvider>);
    expect(screen.getByText("News")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "DE" }));
    expect(screen.getByText("Nachrichten")).toBeTruthy();
    expect(localStorage.getItem("lang")).toBe("de");
    expect(document.documentElement.lang).toBe("de");
  });
});

describe("englische Texte", () => {
  it("lässt keinen Eintrag leer und behält die Platzhalter beider Sprachen", () => {
    for (const [k, v] of Object.entries(DICTS.en)) {
      expect(v.trim(), k).not.toBe("");
      const ph = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join();
      expect(ph(v), k).toBe(ph(DICTS.de[k]));
    }
  });
});
