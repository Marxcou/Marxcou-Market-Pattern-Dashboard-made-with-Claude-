import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { NewsClusterCard } from "../components/NewsClusterCard";
import { api, type InstrumentWithQuote, type SentimentLabel, type Source } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import { useNews, useSentimentStatus } from "../lib/news";

const PERIOD_HOURS = [24, 168, 720, 0];
const SENTIMENTS = ["positiv", "neutral", "negativ"] as const;

export function News() {
  const { t, locale } = useI18n();
  const [params] = useSearchParams();
  const [instrumentId, setInstrumentId] = useState(params.get("instrument") ?? "");
  const [source, setSource] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [hours, setHours] = useState(168);

  const watch = useQuery({ queryKey: ["watchlist"], queryFn: () => api<InstrumentWithQuote[]>("/watchlist") });
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api<Source[]>("/sources") });
  const newsSources = (sources.data ?? []).filter((s) => s.kind === "news");

  const since = hours ? new Date(Date.now() - hours * 3_600_000).toISOString() : undefined;
  // Round to minutes so the query key does not change on every render.
  const stableSince = since ? since.slice(0, 16) + ":00Z" : undefined;
  const news = useNews({
    instrumentId: instrumentId ? Number(instrumentId) : undefined,
    source: source || undefined,
    sentiment: (sentiment || undefined) as SentimentLabel | undefined,
    since: stableSince,
  });

  const pages = news.data?.pages ?? [];
  const items = pages.flatMap((p) => p.items);
  const emptyReason = pages[0]?.empty_reason ?? null;
  const total = pages[0]?.total ?? 0;
  const sstat = useSentimentStatus();

  const usd = (v: number) => v.toLocaleString(locale, { style: "currency", currency: "USD" });
  const sel = "rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm";
  return (
    <section>
      <h1 className="mb-4 ">{t("news.title")}</h1>
      <form className="mb-4 flex flex-wrap gap-3" aria-label={t("news.filter")} onSubmit={(e) => e.preventDefault()}>
        <label className="text-sm">{t("news.stock")}{" "}
          <select className={sel} value={instrumentId} onChange={(e) => setInstrumentId(e.target.value)}>
            <option value="">{t("common.all")}</option>
            {watch.data?.map((i) => <option key={i.id} value={i.id}>{i.symbol}</option>)}
          </select></label>
        <label className="text-sm">{t("news.source")}{" "}
          <select className={sel} value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">{t("common.all")}</option>
            {newsSources.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}
          </select></label>
        <label className="text-sm">{t("news.period")}{" "}
          <select className={sel} value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            {PERIOD_HOURS.map((h) => <option key={h} value={h}>{t(`news.period.${h}` as MessageKey)}</option>)}
          </select></label>
        <label className="text-sm">{t("news.sentiment")}{" "}
          <select className={sel} value={sentiment} onChange={(e) => setSentiment(e.target.value)}>
            <option value="">{t("common.all")}</option>
            {SENTIMENTS.map((s) => <option key={s} value={s}>{t(`sentiment.${s}` as MessageKey)}</option>)}
          </select></label>
      </form>

      {sstat.data && (
        <p className="mb-3 text-xs text-slate-400" data-testid="sentiment-status">
          {t("news.sentimentStatus", { method: t(sstat.data.active_method === "claude" ? "news.methodClaude" : "news.methodLexicon") })}
          {sstat.data.fallback_reason && t("news.fallbackActive", { reason: sstat.data.fallback_reason })}
          {sstat.data.claude_configured && t("news.budget", { month: sstat.data.month, spent: usd(sstat.data.spent_usd), budget: usd(sstat.data.budget_usd) })}
        </p>
      )}
      {news.isLoading && <p className="text-slate-400">{t("news.loading")}</p>}
      {news.isError && <p role="alert" className="text-rose-300">{t("news.loadError")}</p>}
      {news.data && items.length === 0 && (
        <div className="rounded border border-amber-700/50 bg-amber-950/30 p-4 text-amber-200" data-testid="no-news">
          <p className="font-semibold">{t("news.none")}</p>
          <p className="text-sm">{emptyReason ?? t("news.noneHint")}</p>
        </div>
      )}
      {items.length > 0 && (
        <>
          <p className="mb-2 text-xs text-slate-400">{t("news.total", { total })}</p>
          <div className="space-y-4">{items.map((c) => <NewsClusterCard key={c.id} cluster={c} />)}</div>
          {news.hasNextPage && (
            <button type="button" onClick={() => void news.fetchNextPage()} disabled={news.isFetchingNextPage} className="mt-4 rounded border border-slate-700 px-3 py-1 text-sm">
              {news.isFetchingNextPage ? t("common.loading") : t("news.more")}
            </button>
          )}
        </>
      )}
    </section>
  );
}
