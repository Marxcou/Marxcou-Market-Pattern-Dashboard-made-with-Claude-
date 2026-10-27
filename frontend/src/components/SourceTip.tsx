import { formatDateTime } from "../lib/format";
import type { SourceRef } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Grundregel 2: provider, original link, timestamps and delay on every value.
export function SourceTip({ source, ts, fetchedAt }: { source: SourceRef; ts?: string; fetchedAt: string }) {
  const { t } = useI18n();
  return (
    <details className="inline-block text-xs text-slate-400" data-testid="source-tip">
      <summary className="cursor-pointer select-none">{t("source.tip", { name: source.name })}</summary>
      <dl className="mt-1 space-y-0.5 rounded border border-slate-700 bg-slate-900 p-2">
        <div><dt className="inline">{t("source.provider")}</dt><dd className="inline"><a className="underline" href={source.homepage} target="_blank" rel="noreferrer">{source.name}</a></dd></div>
        <div><dt className="inline">{t("source.delay")}</dt><dd className="inline">{source.delay_text}</dd></div>
        {ts && <div><dt className="inline">{t("source.valueTime")}</dt><dd className="inline">{formatDateTime(ts)}</dd></div>}
        <div><dt className="inline">{t("source.fetched")}</dt><dd className="inline">{formatDateTime(fetchedAt)}</dd></div>
        <div><a className="underline" href={source.terms_url} target="_blank" rel="noreferrer">{t("common.termsOfUse")}</a></div>
      </dl>
    </details>
  );
}
