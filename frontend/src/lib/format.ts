// Alle Zahlen- und Datumsformate zentral: Sprache der Oberfläche (en-US oder de-DE), Zeitzone Europe/Berlin (Zeitstempel liegen als UTC vor).
import { getLocale } from "./i18n";

const TZ = "Europe/Berlin";

export const formatNumber = (v: number, digits = 2) =>
  new Intl.NumberFormat(getLocale(), { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);

export const formatPrice = (v: number, currency: string) =>
  new Intl.NumberFormat(getLocale(), { style: "currency", currency }).format(v);

export const formatPercent = (fraction: number) =>
  new Intl.NumberFormat(getLocale(), { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" }).format(fraction);

export const formatDateTime = (iso: string) =>
  new Intl.DateTimeFormat(getLocale(), { dateStyle: "medium", timeStyle: "medium", timeZone: TZ }).format(new Date(iso));

export const formatDate = (iso: string) =>
  new Intl.DateTimeFormat(getLocale(), { dateStyle: "medium", timeZone: TZ }).format(new Date(iso));

// Anteil (0 bis 1) als Prozentangabe ohne Vorzeichen, z. B. 0,62 -> "62 %".
export const formatShare = (fraction: number, digits = 0) =>
  `${new Intl.NumberFormat(getLocale(), { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(fraction * 100)} %`;

// Prozentwert, der schon in Prozent vorliegt (z. B. Rendite -4,1), mit Vorzeichen.
export const formatPercentPoints = (pct: number) =>
  `${new Intl.NumberFormat(getLocale(), { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" }).format(pct)} %`;
