import { Link } from "react-router-dom";
import type { InstrumentWithQuote } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { formatDateTime, formatPercent, formatPrice } from "../lib/format";
import { SourceTip } from "./SourceTip";

export function InstrumentCard({ item, onRemove, newsCount, newsReason, patternCount, patternReason }: { item: InstrumentWithQuote; onRemove?: () => void; newsCount?: number; newsReason?: string | null; patternCount?: number; patternReason?: string | null }) {
  const { t } = useI18n();
  const q = item.quote;
  const tone = q?.change_pct == null ? "text-slate-400" : q.change_pct > 0 ? "text-emerald-400" : q.change_pct < 0 ? "text-rose-400" : "text-slate-300";
  return (
    <article className="card relative transition-colors hover:border-sky-700 hover:bg-slate-900" data-testid="instrument-card">
      <div className="flex items-start justify-between gap-2">
        <Link to={`/instrument/${item.id}`} className="min-w-0 after:absolute after:inset-0 after:rounded-xl">
          <h2 className="font-semibold">{item.symbol}</h2>
          <p className="truncate text-sm text-slate-400">{item.name} · {item.exchange}</p>
        </Link>
        {onRemove && (
          <button type="button" onClick={onRemove} className="relative z-10 -mr-2 -mt-2 rounded-lg px-2 py-2 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-200" aria-label={t("card.removeAria", { symbol: item.symbol })}>
            {t("card.remove")}
          </button>
        )}
      </div>
      {q ? (
        <div className="mt-3">
          <p className="text-2xl font-semibold">{formatPrice(q.price, item.currency)}</p>
          <p className={`text-sm ${tone}`}>
            {q.change_abs != null && `${q.change_abs > 0 ? "+" : ""}${formatPrice(q.change_abs, item.currency)} · `}
            {q.change_pct != null ? formatPercent(q.change_pct / 100) : t("card.noChange")}
          </p>
          <p className="mt-1 text-xs text-slate-400">{t("card.asOf", { time: formatDateTime(q.ts_utc) })}{q.delay_seconds ? t("card.delayed", { min: Math.round(q.delay_seconds / 60) }) : ""}</p>
          {q.is_demo && <p className="text-xs font-semibold text-fuchsia-400">{t("demo.data")}</p>}
          <div className="relative z-10"><SourceTip source={q.source} ts={q.ts_utc} fetchedAt={q.fetched_at} /></div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-amber-300" data-testid="no-quote">{t("card.noQuote")}</p>
      )}
      <p className="mt-3 text-xs text-slate-400" data-testid="news-count">
        {newsCount != null
          ? <>{t("card.newsCount")} <Link to={`/nachrichten?instrument=${item.id}`} className="relative z-10 underline">{newsCount}</Link></>
          : `${t("card.newsNA")}${newsReason ? ` (${newsReason})` : ""}`}
      </p>
      <p className="text-xs text-slate-400" data-testid="pattern-count">
        {patternCount != null
          ? <>{t("card.patternCount")} <Link to={`/instrument/${item.id}`} className="relative z-10 underline">{patternCount}</Link></>
          : `${t("card.patternNA")}${patternReason ? ` (${patternReason})` : ""}`}
      </p>
    </article>
  );
}
