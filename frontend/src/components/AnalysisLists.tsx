import { useState } from "react";
import type { IndicatorEvent, NotableMove, PatternDetection, SRZone } from "../lib/api";
import { eventName, statusText } from "../lib/analysis";
import { useI18n } from "../lib/i18n";
import { formatDate, formatDateTime, formatNumber, formatPercentPoints, formatShare } from "../lib/format";
import { SourceTip } from "./SourceTip";

export function PatternList({ items, selectedId, onSelect }: { items: PatternDetection[]; selectedId: number | null; onSelect: (id: number) => void }) {
  const { t } = useI18n();
  return (
    <ul className="space-y-2" data-testid="pattern-list">
      {items.map((p) => (
        <li key={p.id}>
          <button type="button" onClick={() => onSelect(p.id)} aria-pressed={p.id === selectedId}
            className={`w-full rounded border p-3 text-left text-sm ${p.id === selectedId ? "border-violet-500 bg-violet-950/40" : "border-slate-700"}`}>
            <span className="font-semibold">{p.name}</span>
            <span className="ml-2 text-slate-300">{statusText(p.status, p.status_label)}</span>
            <span className="block text-xs text-slate-400">
              {t("pattern.listLine", { start: formatDate(p.start_ts), end: formatDate(p.end_ts), conf: formatShare(p.confidence.score), bt: p.backtest?.status === "berechnet" && p.backtest.hit_rate != null ? t("pattern.listBacktest", { rate: formatShare(p.backtest.hit_rate), n: p.backtest.sample_size ?? "?" }) : t("common.unavailable") })}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function ZoneList({ zones }: { zones: SRZone[] }) {
  const { t } = useI18n();
  if (zones.length === 0) return null;
  return (
    <div className="mt-4" data-testid="zone-list">
      <h3 className="mb-1 font-semibold">{t("zone.title")}</h3>
      <ul className="space-y-1 text-sm">
        {zones.map((z) => (
          <li key={z.id}>
            <details>
              <summary className="cursor-pointer">{t("zone.summary", { kind: z.kind_label, lower: formatNumber(z.lower), upper: formatNumber(z.upper), touches: z.touch_count, conf: z.confidence ? t("zone.conf", { c: formatShare(z.confidence.score) }) : "" })}</summary>
              <p className="mt-1 text-xs text-slate-300">{z.explanation}</p>
              <p className="text-xs text-slate-400">{t("zone.touches", { first: formatDate(z.first_touch), last: formatDate(z.last_touch) })}</p>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EventList({ events }: { events: IndicatorEvent[] }) {
  const { t } = useI18n();
  return (
    <ul className="space-y-2" data-testid="event-list">
      {events.map((e) => (
        <li key={e.id} className="rounded border border-slate-800 p-3 text-sm" data-testid="indicator-event">
          <p className="font-semibold">{e.title || eventName(e.type)} <span className="font-normal text-slate-400">· {formatDate(e.ts)}</span></p>
          <p className="text-slate-300">{e.summary}</p>
          <details className="mt-1 text-xs text-slate-300">
            <summary className="cursor-pointer text-slate-400">{t("event.details")}</summary>
            <table className="mt-1 w-full text-left">
              <thead className="text-slate-400"><tr><th>{t("event.colCriterion")}</th><th>{t("event.colRule")}</th><th>{t("event.colRequired")}</th><th>{t("event.colActual")}</th><th>{t("event.colResult")}</th></tr></thead>
              <tbody>{e.criteria.map((c) => <tr key={c.name} className="border-t border-slate-800"><td>{c.name}</td><td>{c.rule}</td><td>{c.required}</td><td>{c.actual}</td><td>{c.passed ? t("common.passed") : t("common.failed")}</td></tr>)}</tbody>
            </table>
            <p className="mt-1">{t("event.params", { params: Object.entries(e.params).map(([k, v]) => `${k} = ${String(v)}`).join(", ") || t("event.none"), v: e.algo_version })}</p>
            <p className="mt-1" data-testid="event-stats">{e.historical_stats ? t("event.statsAvailable") : (e.historical_stats_reason ?? t("event.statsNA"))}</p>
            <div className="mt-1 flex flex-wrap gap-2">{e.sources.map((s) => <SourceTip key={s.key} source={s} fetchedAt={e.bars_fetched_at} />)}</div>
          </details>
        </li>
      ))}
    </ul>
  );
}

export function MoveList({ moves, note, onOpenNews }: { moves: NotableMove[]; note: string; onOpenNews: (clusterId: number) => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div data-testid="move-list">
      <p className="mb-2 text-xs text-slate-400">{note} {t("move.windowNote")}</p>
      <ul className="space-y-2">
        {moves.map((m) => (
          <li key={m.id} className="rounded border border-slate-800 p-3 text-sm" data-testid="move">
            <p>
              {t("move.notable", { start: formatDate(m.move_start), end: formatDate(m.move_end), ret: formatPercentPoints(m.return_pct) })}
              <span className="text-xs text-slate-400"> ({m.return_z != null ? t("move.dev", { z: formatNumber(m.return_z, 1) }) : t("move.devNA")}{m.volume_z != null ? t("move.vol", { v: formatNumber(m.volume_z, 1) }) : ""})</span>
            </p>
            {m.news.length === 0 ? (
              <p className="text-xs text-slate-400">{t("move.noNews")}</p>
            ) : (
              <>
                <p className="text-xs text-slate-300">{t("move.coinciding", { n: m.news.length })}</p>
                <ul className="mt-1 space-y-1">
                  {m.news.map((n) => (
                    <li key={n.cluster_id}>
                      <button type="button" className="text-left underline" onClick={() => { setOpen(n.cluster_id); onOpenNews(n.cluster_id); }}>{n.canonical_title}</button>
                      <span className="block text-xs text-slate-400">
                        {t("move.offset", { time: formatDateTime(n.first_published_at), min: Math.abs(n.time_offset_minutes), dir: t(n.time_offset_minutes < 0 ? "move.before" : "move.after"), count: n.item_count, src: t(n.item_count === 1 ? "common.source" : "common.sources"), names: n.sources.map((s) => s.name).join(", ") })}
                        {open === n.cluster_id && t("move.opened")}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <details className="mt-1 text-xs text-slate-400"><summary className="cursor-pointer">{t("move.method")}</summary>
              <p>{t("move.methodText", { z: String(m.params.z_threshold ?? "?"), n: String(m.params.lookback_bars ?? "?"), v: m.algo_version })}</p>
              <div className="flex flex-wrap gap-2">{m.sources.map((s) => <SourceTip key={s.key} source={s} fetchedAt={m.bars_fetched_at} />)}</div>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}
