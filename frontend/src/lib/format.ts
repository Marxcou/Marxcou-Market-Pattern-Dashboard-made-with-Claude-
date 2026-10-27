// All number and date formats in one place: interface language (en-US or de-DE), time zone Europe/Berlin (timestamps are stored as UTC).
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

// Share (0 to 1) as a percentage without sign, e.g. 0.62 -> "62%".
export const formatShare = (fraction: number, digits = 0) =>
  `${new Intl.NumberFormat(getLocale(), { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(fraction * 100)} %`;

// Percentage value that is already in percent (e.g. return -4.1), with sign.
export const formatPercentPoints = (pct: number) =>
  `${new Intl.NumberFormat(getLocale(), { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" }).format(pct)} %`;
