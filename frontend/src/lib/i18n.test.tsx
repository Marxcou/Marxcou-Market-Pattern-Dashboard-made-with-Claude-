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
    render(<LanguageProvider><LanguageSwitch /><Probe /></LanguageProvider>);
    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.getByText("News")).toBeTruthy();
    expect(localStorage.getItem("lang")).toBe("en");
    expect(document.documentElement.lang).toBe("en");
  });
});
