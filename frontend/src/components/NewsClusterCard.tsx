import type { NewsCluster } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useI18n, type MessageKey } from "../lib/i18n";
import { SourceTip } from "./SourceTip";

// Neutrale Darstellung: die Stimmung ist eine Beschreibung des Textes, kein Signal und keine Handlungsaufforderung.
export function SentimentInfo({ s }: { s: NonNullable<NewsCluster["sentiment"]> }) {
  const { t, locale } = useI18n();
  const label = ["positiv", "neutral", "negativ"].includes(s.label) ? t(`sentiment.${s.label}` as MessageKey) : s.label;
  const method = s.method === "claude" ? t("news.methodAi", { model: s.model_name })
    : t("news.methodWordlist", { name: s.model_name, version: s.model_version ? t("news.version", { v: s.model_version }) : "" });
  return (
    <details className="text-xs text-slate-300" data-testid="sentiment">
      <summary className="cursor-pointer">{t("news.sentimentSummary", { label, score: s.score.toLocaleString(locale, { maximumFractionDigits: 2 }), method })}</summary>
      <p className="mt-1">{s.rationale}</p>
      {s.evidence.length > 0 && (
        <ul className="mt-1 list-disc pl-5">{s.evidence.map((e) => <li key={e}>“{e}”</li>)}</ul>
      )}
    </details>
  );
}

export function NewsClusterCard({ cluster }: { cluster: NewsCluster }) {
  const { t } = useI18n();
  return (
    <article className="rounded-lg border border-slate-800 bg-slate-900 p-4" data-testid="news-cluster">
      <h2 className="font-semibold">{cluster.canonical_title}</h2>
      <p className="text-xs text-slate-400">
        {t("news.firstPublished", { time: formatDateTime(cluster.first_published_at) })}
        {cluster.instruments.length > 0 && ` · ${cluster.instruments.map((i) => i.symbol).join(", ")}`}
        {` · ${cluster.item_count} ${t(cluster.item_count === 1 ? "common.source" : "common.sources")}`}
      </p>
      {cluster.sentiment ? <div className="mt-2"><SentimentInfo s={cluster.sentiment} /></div>
        : <p className="mt-2 text-xs text-slate-400">{t("news.noSentiment")}</p>}
      <ul className="mt-3 space-y-3">
        {cluster.items.map((it) => (
          <li key={it.id} className="border-l-2 border-slate-700 pl-3" data-testid="news-item">
            <a href={it.url} target="_blank" rel="noreferrer" className="text-sm text-sky-300 underline">{it.title}</a>
            {it.excerpt && <p className="text-sm text-slate-300">{it.excerpt}</p>}
            <p className="text-xs text-slate-400">{it.source.name} · {t("news.published", { time: formatDateTime(it.published_at) })}</p>
            <SourceTip source={it.source} ts={it.published_at} fetchedAt={it.fetched_at} />
          </li>
        ))}
      </ul>
    </article>
  );
}
