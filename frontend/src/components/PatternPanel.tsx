import type { PatternBacktest, PatternDetection } from "../lib/api";
import { formatDate, formatDateTime, formatNumber, formatPercentPoints, formatShare } from "../lib/format";
import { levelLabels, statusText } from "../lib/analysis";
import { tr, useI18n, type MessageKey } from "../lib/i18n";
import { AiExplanation } from "./AiExplanation";
import { SourceTip } from "./SourceTip";

const MIN_SAMPLE_HINT = 30;

// Grundregel 3: anything missing is stated explicitly instead of being hidden or filled in.
export function missingParts(p: PatternDetection): string[] {
  const m: string[] = [];
  if (p.criteria.length === 0) m.push(tr("pattern.missing.criteria"));
  if (!p.confidence?.breakdown?.length) m.push(tr("pattern.missing.breakdown"));
  if (p.scenarios.length < 2) m.push(tr("pattern.missing.scenarios"));
  if (p.confirmation_level == null || p.invalidation_level == null) m.push(tr("pattern.missing.levels"));
  return m;
}

export function BacktestBlock({ b }: { b: PatternBacktest | null }) {
  const { t } = useI18n();
  if (!b || b.status !== "berechnet" || b.hit_rate == null || b.sample_size == null) {
    return (
      <div className="rounded border border-amber-700/50 bg-amber-950/30 p-3 text-sm text-amber-200" data-testid="backtest-missing">
        <p className="font-semibold">{t("bt.missing")}</p>
        <p>{b?.note ?? t("bt.missingNote")}</p>
      </div>
    );
  }
  const horizon = b.horizon_bars != null ? t("bt.withinBars", { n: b.horizon_bars }) : t("bt.withinPeriod");
  const move = b.min_move_pct != null ? t("bt.byAtLeast", { v: formatNumber(b.min_move_pct, 1) }) : "";
  return (
    <div className="rounded border border-slate-700 p-3 text-sm" data-testid="backtest">
      <p>{t("bt.sentence", { rate: formatShare(b.hit_rate), n: b.sample_size, move, horizon })}</p>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-300 sm:grid-cols-4">
        <div><dt className="text-slate-400">{t("bt.sampleSize")}</dt><dd>{b.sample_size}</dd></div>
        <div><dt className="text-slate-400">{t("bt.ci")}</dt><dd>{b.ci_low != null && b.ci_high != null ? `${formatShare(b.ci_low)} ${t("common.to")} ${formatShare(b.ci_high)}` : t("common.unavailable")}</dd></div>
        <div><dt className="text-slate-400">{t("bt.baseRate")}</dt><dd>{b.base_rate != null ? formatShare(b.base_rate) : t("common.unavailable")}</dd></div>
        <div><dt className="text-slate-400">{t("bt.run")}</dt><dd>{b.computed_at ? formatDate(b.computed_at) : t("bt.runNo", { n: b.run_id ?? "?" })}</dd></div>
      </dl>
      {b.not_better_than_random && <p className="mt-2 font-semibold text-amber-300" data-testid="not-better">{t("bt.notBetter")}{b.verdict_text ? ` ${b.verdict_text}` : ""}</p>}
      {b.not_better_than_random === false && b.verdict_text && <p className="mt-2 text-xs text-slate-300">{b.verdict_text}</p>}
      {b.mean_return_pct != null && b.horizon_bars != null && (
        <p className="mt-2 text-xs text-slate-300" data-testid="backtest-return">
          {t("bt.meanReturn", { n: b.horizon_bars, v: formatPercentPoints(b.mean_return_pct) })}
          {b.median_return_pct != null && t("bt.median", { v: formatPercentPoints(b.median_return_pct) })}
          {b.base_mean_return_pct != null && t("bt.allDays", { v: formatPercentPoints(b.base_mean_return_pct) })}.
        </p>
      )}
      {b.sample_size < MIN_SAMPLE_HINT && <p className="mt-1 text-xs text-amber-300">{t("bt.small", { n: MIN_SAMPLE_HINT })}</p>}
      <p className="mt-2 text-xs text-slate-400">
        {b.universe && t("bt.universe", { v: b.universe })}{b.date_range && t("bt.range", { v: b.date_range })}{b.survivorship_note}
      </p>
      {b.note && <p className="mt-1 text-xs text-slate-400">{b.note}</p>}
      {(b.method || b.source) && (
        <details className="mt-1 text-xs text-slate-400">
          <summary className="cursor-pointer">{t("bt.how")}</summary>
          {b.method && <p className="mt-1">{b.method}</p>}
          {b.source && <p className="mt-1">{t("bt.sourceLine")}<a className="underline" href={b.source.homepage} target="_blank" rel="noreferrer">{b.source.name}</a>{b.source.fetched_to && t("bt.fetched", { v: formatDate(b.source.fetched_to) })}</p>}
        </details>
      )}
    </div>
  );
}

export function PatternPanel({ p, onClose }: { p: PatternDetection; onClose?: () => void }) {
  const { t } = useI18n();
  const missing = missingParts(p);
  const labels = levelLabels(p.direction_if_confirmed);
  return (
    <article className="rounded-lg border border-violet-800/60 bg-slate-900 p-4" data-testid="pattern-panel" aria-label={t("pattern.aria", { name: p.name })}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{p.name}</h2>
          <p className="text-sm text-slate-300">
            {t("pattern.status")}<span data-testid="pattern-status">{statusText(p.status, p.status_label)}</span>
            {t(`pattern.dir.${p.direction_if_confirmed}` as MessageKey)}
          </p>
          <p className="text-xs text-slate-400" data-testid="pattern-range">{t("pattern.location", { start: formatDate(p.start_ts), end: formatDate(p.end_ts), tf: p.timeframe })}</p>
        </div>
        {onClose && <button type="button" onClick={onClose} className="rounded border border-slate-700 px-2 py-1 text-xs">{t("common.close")}</button>}
      </header>

      {missing.length > 0 && (
        <p role="alert" className="mt-3 rounded border border-rose-700/60 bg-rose-950/40 p-2 text-sm text-rose-200" data-testid="pattern-incomplete">
          {t("pattern.incomplete", { parts: missing.join(", ") })}
        </p>
      )}

      {p.explanation && <p className="mt-3 text-sm" data-testid="pattern-explanation">{p.explanation}</p>}
      <AiExplanation kind="pattern" id={p.id} />

      <section className="mt-4" aria-labelledby={`k-${p.id}`}>
        <h3 id={`k-${p.id}`} className="mb-1 font-semibold">{t("pattern.keyPoints")}</h3>
        <ul className="text-sm text-slate-300">
          {p.key_points.map((k) => <li key={`${k.role}-${k.ts}`}>{t("pattern.keyPoint", { label: k.label, price: formatNumber(k.price), date: formatDate(k.ts) })}</li>)}
        </ul>
      </section>

      <section className="mt-4" aria-labelledby={`c-${p.id}`}>
        <h3 id={`c-${p.id}`} className="mb-1 font-semibold">{t("pattern.criteria")}</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-sm" data-testid="criteria-table">
            <thead className="text-xs text-slate-400"><tr><th className="pr-2">{t("pattern.colCriterion")}</th><th className="pr-2">{t("pattern.colRule")}</th><th className="pr-2">{t("pattern.colActual")}</th><th className="pr-2">{t("pattern.colResult")}</th><th className="pr-2 text-right">{t("pattern.colSub")}</th><th className="text-right">{t("pattern.colWeight")}</th></tr></thead>
            <tbody>
              {p.criteria.map((c) => (
                <tr key={c.key} className="border-t border-slate-800 align-top">
                  <td className="py-1 pr-2">{c.name}{!c.required && <span className="block text-xs text-slate-400">{t("pattern.quality")}</span>}</td>
                  <td className="py-1 pr-2 text-slate-300">{c.rule}</td>
                  <td className="py-1 pr-2">{c.actual_text}</td>
                  <td className="py-1 pr-2">{c.passed ? t("common.passed") : t("common.failed")}</td>
                  <td className="py-1 pr-2 text-right">{formatNumber(c.sub_score)}</td>
                  <td className="py-1 text-right">{formatNumber(c.weight)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-4" aria-labelledby={`f-${p.id}`}>
        <h3 id={`f-${p.id}`} className="mb-1 font-semibold">{t("pattern.confidence")}<span data-testid="confidence">{formatShare(p.confidence.score)}</span></h3>
        <p className="text-sm text-slate-300">{p.confidence.method}</p>
        <p className="mt-1 text-xs text-slate-400">{t("pattern.confidenceNote")}</p>
        <table className="mt-2 w-full max-w-xl text-left text-sm" data-testid="confidence-table">
          <thead className="text-xs text-slate-400"><tr><th>{t("pattern.colCriterion")}</th><th className="text-right">{t("pattern.colWeight")}</th><th className="text-right">{t("pattern.colSub")}</th><th className="text-right">{t("pattern.colContribution")}</th></tr></thead>
          <tbody>
            {p.confidence.breakdown.map((b) => (
              <tr key={b.key} className="border-t border-slate-800"><td className="py-0.5">{b.name}</td><td className="text-right">{formatNumber(b.weight)}</td><td className="text-right">{formatNumber(b.sub_score)}</td><td className="text-right">{formatNumber(b.contribution, 3)}</td></tr>
            ))}
            <tr className="border-t border-slate-600 font-semibold"><td>{t("pattern.total")}</td><td /><td /><td className="text-right">{formatNumber(p.confidence.breakdown.reduce((s, b) => s + b.contribution, 0), 3)}</td></tr>
          </tbody>
        </table>
      </section>

      <section className="mt-4" aria-labelledby={`s-${p.id}`}>
        <h3 id={`s-${p.id}`} className="mb-1 font-semibold">{t("pattern.scenarios")}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {p.scenarios.map((s) => (
            <div key={s.kind} className="rounded border border-slate-700 p-3 text-sm" data-testid="scenario">
              <h4 className="font-semibold">{s.title}</h4>
              <p className="text-slate-300">{s.trigger_rule}</p>
              <p className="mt-1 text-xs text-slate-400">{t("pattern.level", { v: s.trigger_level != null ? formatNumber(s.trigger_level) : t("common.unavailable") })}</p>
              <p className="mt-1">{s.description}</p>
              {s.historical?.text && <p className="mt-1 text-xs text-slate-300">{t("pattern.historical", { text: s.historical.text })}{s.historical.sample_size != null ? t("pattern.historicalN", { n: s.historical.sample_size }) : ""}</p>}
            </div>
          ))}
        </div>
        <p className="mt-2 text-sm" data-testid="levels">
          {t("pattern.levelsLine", { a: labels.confirmation, av: p.confirmation_level != null ? formatNumber(p.confirmation_level) : t("common.unavailable"), b: labels.invalidation, bv: p.invalidation_level != null ? formatNumber(p.invalidation_level) : t("common.unavailable") })}
        </p>
        <p className="text-xs text-slate-400">{t(p.direction_if_confirmed === "offen" ? "pattern.levelsOpen" : "pattern.levelsDir")}</p>
      </section>

      <section className="mt-4" aria-labelledby={`b-${p.id}`}>
        <h3 id={`b-${p.id}`} className="mb-1 font-semibold">{t("pattern.backtestTitle")}</h3>
        <BacktestBlock b={p.backtest} />
      </section>

      <details className="mt-4 text-xs text-slate-400">
        <summary className="cursor-pointer">{t("pattern.method")}</summary>
        <p className="mt-1">{t("pattern.methodText", { v: p.algo_version, hash: p.params_hash, time: formatDateTime(p.detected_at) })}</p>
        <pre className="mt-1 overflow-x-auto rounded bg-slate-950 p-2">{JSON.stringify(p.params, null, 2)}</pre>
        <p className="mt-1">{t("pattern.basis", { n: p.data_basis.bar_count, from: formatDate(p.data_basis.bars_from), to: formatDate(p.data_basis.bars_to), time: formatDateTime(p.data_basis.last_fetched_at) })}</p>
        <div className="mt-1 flex flex-wrap gap-2">{p.data_basis.sources.map((s) => <SourceTip key={s.key} source={s} fetchedAt={p.data_basis.last_fetched_at} />)}</div>
      </details>
    </article>
  );
}
