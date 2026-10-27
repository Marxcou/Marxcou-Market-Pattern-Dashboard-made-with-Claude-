import type { ForecastBacktest, ForecastMedianLine, ForecastResponse, ForecastStep, PatternDetection } from "../lib/api";
import { BAND_FILL, BANDS, EXAMPLE_COLOR, HORIZONS, MEDIAN_COLOR, validExamplePaths, coverageNote, levelPosition, metricName, metricVsNaive, scenarioLevels, validSteps } from "../lib/forecast";
import { formatDate, formatDateTime, formatNumber, formatShare } from "../lib/format";
import { getLocale, useI18n } from "../lib/i18n";
import { AiExplanation } from "./AiExplanation";
import { SourceTip } from "./SourceTip";

const money = (v: number, currency: string) => new Intl.NumberFormat(getLocale(), { style: "currency", currency }).format(v);

// Grundregel 4: forecast quality compared with the naive reference "price stays the same"; if the backtest is missing, that is stated explicitly.
export function ForecastBacktestBlock({ b }: { b: ForecastBacktest | null }) {
  const { t } = useI18n();
  if (!b || b.status !== "berechnet" || b.sample_size == null) {
    return (
      <div className="rounded border border-amber-700/50 bg-amber-950/30 p-3 text-sm text-amber-200" data-testid="forecast-backtest-missing">
        <p className="font-semibold">{t("fcbt.missing")}</p>
        <p>{b?.note ?? t("fcbt.missingNote")}</p>
      </div>
    );
  }
  return (
    <div className="rounded border border-slate-700 p-3 text-sm" data-testid="forecast-backtest">
      <p className="font-semibold">{t("fcbt.title")}</p>
      <p className="text-xs text-slate-400">
        {t("fcbt.sample", { n: b.sample_size })}{b.horizon_bars != null && t("fcbt.perHorizon", { n: b.horizon_bars })}{b.universe && ` · ${b.universe}`}{b.date_range && ` · ${b.date_range}`}
      </p>
      {b.coverage && b.coverage.length > 0 && (
        <table className="mt-2 w-full text-xs" data-testid="coverage-table">
          <caption className="pb-1 text-left text-slate-400">{t("fcbt.coverageCaption")}</caption>
          <thead><tr className="text-left text-slate-400"><th className="py-1">{t("fcbt.colBand")}</th><th>{t("fcbt.colNominal")}</th><th>{t("fcbt.colObserved")}</th><th>{t("fcbt.colAssessment")}</th></tr></thead>
          <tbody>{b.coverage.map((c) => (
            <tr key={c.nominal} className="border-t border-slate-800"><td className="py-1">{Math.round(c.nominal * 100)} %</td><td>{formatShare(c.nominal)}</td><td>{formatShare(c.observed, 1)}</td><td>{coverageNote(c.nominal, c.observed)}</td></tr>
          ))}</tbody>
        </table>
      )}
      {b.metrics && b.metrics.length > 0 && (
        <table className="mt-3 w-full text-xs" data-testid="metrics-table">
          <caption className="pb-1 text-left text-slate-400">{t("fcbt.metricsCaption")}</caption>
          <thead><tr className="text-left text-slate-400"><th className="py-1">{t("fcbt.colMeasure")}</th><th>{t("fcbt.colMethod")}</th><th>{t("fcbt.colReference")}</th><th>{t("fcbt.colComparison")}</th></tr></thead>
          <tbody>{b.metrics.map((m) => {
            const v = metricVsNaive(m);
            return (
              <tr key={m.key} className="border-t border-slate-800">
                <td className="py-1">{metricName(m)}</td><td>{m.model != null ? `${formatNumber(m.model, 2)}${m.unit ? ` ${m.unit}` : ""}` : t("common.unavailable")}</td><td>{m.naive != null ? `${formatNumber(m.naive, 2)}${m.unit ? ` ${m.unit}` : ""}` : t("common.unavailable")}</td>
                <td>{v.ratio != null && t("fcbt.times", { v: formatNumber(v.ratio, 2) })}{v.text}</td>
              </tr>
            );
          })}</tbody>
        </table>
      )}
      {b.skill != null && <p className="mt-2 text-xs text-slate-300" data-testid="skill">{t("fcbt.skill", { v: formatNumber(b.skill * 100, 1) })}{b.dm_p_value != null && t("fcbt.dm", { v: formatNumber(b.dm_p_value, 2) })}.</p>}
      {b.by_horizon && b.by_horizon.length > 0 && (
        <table className="mt-3 w-full text-xs" data-testid="horizon-backtest-table">
          <caption className="pb-1 text-left text-slate-400">{t("fcbt.byHorizon")}</caption>
          <thead><tr className="text-left text-slate-400"><th className="py-1">{t("fcbt.colHorizon")}</th><th>{t("fc.colSample")}</th><th>{t("fcbt.colImprovement")}</th><th>{t("fcbt.colP")}</th><th>{t("fcbt.colBetter")}</th></tr></thead>
          <tbody>{b.by_horizon.map((h) => (
            <tr key={h.horizon_bars} className="border-t border-slate-800">
              <td className="py-1">{t("fcbt.candles", { n: h.horizon_bars })}</td><td>{h.sample_size ?? "?"}</td><td>{h.skill != null ? `${formatNumber(h.skill * 100, 1)} %` : t("common.unavailable")}</td>
              <td>{h.dm_p_value != null ? formatNumber(h.dm_p_value, 2) : t("common.unavailable")}</td><td>{h.better_than_naive == null ? t("fcbt.notAssessable") : t(h.better_than_naive ? "fcbt.yesProven" : "fcbt.notProven")}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {b.better_than_naive === false && <p className="mt-2 font-semibold text-amber-300" data-testid="not-better-naive">{t("fcbt.notBetter")}{b.verdict_text ? ` ${b.verdict_text}` : ""}</p>}
      {b.better_than_naive === true && b.verdict_text && <p className="mt-2 text-xs text-slate-300">{b.verdict_text}</p>}
      {b.better_than_naive == null && <p className="mt-2 text-xs text-amber-300">{t("fcbt.noComparison")}</p>}
      {b.sample_size < 30 && <p className="mt-1 text-xs text-amber-300">{t("fcbt.small")}</p>}
    </div>
  );
}

// Central path (Grundregel 4): only as the middle of the corridor, always with the backtest error of this line per horizon.
function MedianLineBlock({ line, shown }: { line: ForecastMedianLine | null | undefined; shown: boolean }) {
  const { t } = useI18n();
  const errors = line?.errors ?? [];
  return (
    <div data-testid="median-line">
      <h3 className="text-sm font-semibold"><span className="mr-2 inline-block w-5 border-t-2 border-dashed align-middle" style={{ borderColor: MEDIAN_COLOR }} />{line?.name ?? t("fc.medianDefaultName")}</h3>
      <p className="mt-1 text-xs text-slate-300">{line?.description ?? t("fc.medianFallback")}</p>
      {!shown && <p className="mt-1 text-xs text-slate-400">{t("fc.medianHidden")}</p>}
      {errors.length > 0 ? (
        <table className="mt-2 w-full text-xs" data-testid="median-error-table">
          <caption className="pb-1 text-left text-slate-400">{t("fc.medianCaption")}</caption>
          <thead><tr className="text-left text-slate-400"><th className="py-1">{t("fc.colAfter")}</th><th>{t("fc.colDeviation")}</th><th>{t("fc.colNaive")}</th><th>{t("fc.colSample")}</th></tr></thead>
          <tbody>{errors.map((e) => (
            <tr key={e.horizon_bars} className="border-t border-slate-800">
              <td className="py-1">{t("fc.afterDays", { n: e.horizon_bars })}</td>
              <td>{e.model != null ? `± ${formatNumber(e.model, 2)} %` : t("common.unavailable")}</td>
              <td>{e.naive != null ? `± ${formatNumber(e.naive, 2)} %` : t("common.unavailable")}</td>
              <td>{t("fc.nForecasts", { n: e.sample_size ?? "?" })}</td>
            </tr>
          ))}</tbody>
        </table>
      ) : (
        <p className="mt-2 text-xs text-amber-300" data-testid="median-error-missing">{t("fc.medianMissing")}</p>
      )}
    </div>
  );
}

function HorizonTable({ steps, currency, lastClose }: { steps: ForecastStep[]; currency: string; lastClose: number | null }) {
  const { t } = useI18n();
  const last = steps[steps.length - 1];
  return (
    <table className="mt-2 w-full text-xs" data-testid="horizon-table">
      <caption className="pb-1 text-left text-slate-400">{t("fc.tableCaption", { date: formatDate(last.ts) })}</caption>
      <thead><tr className="text-left text-slate-400"><th className="py-1">{t("fc.colRange")}</th><th>{t("fc.colFrom")}</th><th>{t("fc.colTo")}</th>{lastClose != null && <th>{t("fc.colDistance")}</th>}</tr></thead>
      <tbody>{[...BANDS].reverse().map((b) => {
        const lo = last.quantiles[b.lower], hi = last.quantiles[b.upper];
        return (
          <tr key={b.level} className="border-t border-slate-800">
            <td className="py-1"><span className="mr-2 inline-block h-2 w-4 align-middle" style={{ background: BAND_FILL[b.level] }} />{b.level} %</td>
            <td>{money(lo, currency)}</td><td>{money(hi, currency)}</td>
            {lastClose != null && <td>{t("fc.distance", { a: formatNumber(((lo / lastClose) - 1) * 100, 1), b: formatNumber(((hi / lastClose) - 1) * 100, 1) })}</td>}
          </tr>
        );
      })}</tbody>
    </table>
  );
}

export function ForecastPanel({ data, loading, error, horizon, onHorizon, currency, pattern, showMedian = true, showExamples = false }: {
  data: ForecastResponse | undefined; loading: boolean; error: boolean; horizon: number; onHorizon: (h: number) => void; currency: string; pattern: PatternDetection | null;
  showMedian?: boolean; showExamples?: boolean;
}) {
  const { t } = useI18n();
  const examples = validExamplePaths(data?.example_paths);
  const steps = validSteps(data?.steps ?? []);
  currency = data?.currency ?? currency;
  const last = steps[steps.length - 1];
  const levels = scenarioLevels(pattern);
  const link = pattern ? data?.pattern_scenarios?.find((l) => l.detection_id === pattern.id) ?? null : null;
  return (
    <section className="rounded-lg border border-sky-900/60 bg-slate-900 p-4" data-testid="forecast-panel" aria-label={t("fc.title")}>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-semibold">{t("fc.title")}</h2>
        <div role="group" aria-label={t("fc.horizon")} className="flex gap-1">
          {HORIZONS.map((h) => (
            <button key={h} type="button" aria-pressed={h === horizon} onClick={() => onHorizon(h)} className={`rounded border px-2 py-0.5 text-xs ${h === horizon ? "border-sky-500 bg-sky-900" : "border-slate-700"}`}>{t("fc.days", { n: h })}</button>
          ))}
        </div>
      </div>
      <p className="mt-1 text-xs text-slate-400" data-testid="forecast-note">{data?.note ? `${data.note} ` : ""}{t("fc.noteTail")}</p>

      {data?.is_demo && <p className="mt-2 text-xs font-semibold text-fuchsia-300" data-testid="forecast-demo">{t("fc.demo")}</p>}
      {loading && <p className="mt-2 text-sm text-slate-400">{t("fc.loading")}</p>}
      {error && <p role="alert" className="mt-2 text-sm text-rose-300">{t("fc.error")}</p>}
      {data?.pending && <p className="mt-2 text-sm text-slate-300" role="status" data-testid="forecast-pending">{t("fc.pending", { reason: data.empty_reason ?? "" })}</p>}
      {data?.empty_reason && !data.pending && <p className="mt-2 text-sm text-amber-300" data-testid="no-forecast">{t("fc.none", { reason: data.empty_reason ?? "" })}</p>}
      {data && !data.empty_reason && steps.length === 0 && <p className="mt-2 text-sm text-amber-300" data-testid="no-forecast">{t("fc.incomplete")}</p>}

      {data && steps.length > 0 && (
        <div className="mt-3 space-y-4">
          <AiExplanation kind="forecast" id={data.instrument_id} />
          <p className="text-xs text-slate-300" data-testid="forecast-basis">
            {t("fc.basis", { until: data.based_on_until ? formatDateTime(data.based_on_until) : t("chart.timeNA"), generated: data.generated_at ? t("fc.generated", { v: formatDateTime(data.generated_at) }) : "", method: data.method?.name ?? t("fc.methodNA"), v: data.algo_version || "?" })}
          </p>
          <ul className="flex flex-wrap gap-3 text-xs" data-testid="forecast-legend" aria-label={t("fc.legendBands")}>
            {[...BANDS].reverse().map((b) => (<li key={b.level}><span className="mr-1 inline-block h-3 w-5 align-middle" style={{ background: BAND_FILL[b.level] }} />{t("fc.band", { n: b.level })}</li>))}
          </ul>
          <ul className="flex flex-wrap gap-3 text-xs" data-testid="forecast-line-legend" aria-label={t("fc.legendLines")}>
            <li><span className="mr-1 inline-block w-5 border-t-2 border-dashed align-middle" style={{ borderColor: MEDIAN_COLOR }} />{t("fc.medianLegend")}{!showMedian && t("fc.hidden")}</li>
            {examples.length > 0 && <li><span className="mr-1 inline-block w-5 border-t align-middle" style={{ borderColor: EXAMPLE_COLOR }} />{t("fc.examplesLegend", { n: examples.length })}{!showExamples && t("fc.hidden")}</li>}
          </ul>
          <HorizonTable steps={steps} currency={currency} lastClose={data.last_close} />
          <MedianLineBlock line={data.median_line} shown={showMedian} />
          {examples.length > 0 && (
            <div data-testid="example-paths">
              <h3 className="text-sm font-semibold"><span className="mr-2 inline-block w-5 border-t align-middle" style={{ borderColor: EXAMPLE_COLOR }} />{t("fc.examples")}</h3>
              <p className="mt-1 text-xs text-slate-300">{data.example_paths_note ?? t("fc.examplesFallback")}</p>
              {!showExamples && <p className="mt-1 text-xs text-slate-400">{t("fc.examplesHidden")}</p>}
            </div>
          )}

          {pattern && levels.length > 0 && (
            <div data-testid="scenario-levels">
              <h3 className="text-sm font-semibold">{t("fc.levelsTitle", { name: pattern.name })}</h3>
              <ul className="mt-1 space-y-1 text-xs">
                {levels.map((l) => (
                  <li key={l.key}><span className="text-slate-100">{l.label}: {money(l.price, currency)}</span>
                    {data.last_close != null && t("fc.levelDistance", { v: formatNumber((l.price / data.last_close - 1) * 100, 1) })} – {levelPosition(l.price, last).text}.</li>
                ))}
              </ul>
              <p className="mt-1 text-xs text-slate-400">{t("fc.levelsNote")}</p>
            </div>
          )}
          {link && (
            <div data-testid="pattern-scenario-link">
              <h3 className="text-sm font-semibold">{t("fc.linkTitle", { name: link.name })}</h3>
              <table className="mt-1 w-full text-xs">
                <thead><tr className="text-left text-slate-400"><th className="py-1">{t("fc.colScenario")}</th><th>{t("fc.colLevel")}</th><th>{t("fc.colSimulated")}</th><th>{t("fc.colHistorical")}</th></tr></thead>
                <tbody>{link.scenarios.map((sc) => (
                  <tr key={sc.kind} className="border-t border-slate-800 align-top">
                    <td className="py-1">{sc.title}</td><td>{sc.trigger_level != null ? money(sc.trigger_level, currency) : "?"}</td>
                    <td>{sc.model_probability_text ?? (sc.model_probability != null ? formatShare(sc.model_probability) : t("common.unavailable"))}</td>
                    <td>{sc.historical?.share != null ? t("fc.historicalOf", { share: formatShare(sc.historical.share), n: sc.historical.sample_size ?? "?" }) : t("fc.historicalNA")}</td>
                  </tr>
                ))}</tbody>
              </table>
              {link.neither_probability != null && <p className="mt-1 text-xs text-slate-300">{t("fc.neither", { share: formatShare(link.neither_probability) })}</p>}
              <p className="mt-1 text-xs text-slate-400">{link.note}</p>
            </div>
          )}

          <details className="text-xs" data-testid="forecast-method">
            <summary className="cursor-pointer font-semibold text-slate-200">{t("fc.how")}</summary>
            <p className="mt-1 text-slate-300">{data.method?.description ?? t("fc.noDescription")}</p>
            {data.method?.assumptions && data.method.assumptions.length > 0 && <><p className="mt-2 font-semibold text-slate-300">{t("fc.assumptions")}</p><ul className="list-disc pl-5 text-slate-300">{data.method.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></>}
            {data.method?.limitations && data.method.limitations.length > 0 && <><p className="mt-2 font-semibold text-slate-300">{t("fc.limitations")}</p><ul className="list-disc pl-5 text-slate-300">{data.method.limitations.map((a) => <li key={a}>{a}</li>)}</ul></>}
            {data.method?.params && Object.keys(data.method.params).length > 0 && (
              <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 sm:grid-cols-3">{Object.entries(data.method.params).map(([k, v]) => (<div key={k}><dt className="inline text-slate-400">{k}: </dt><dd className="inline">{String(v)}</dd></div>))}</dl>
            )}
          </details>

          <ForecastBacktestBlock b={data.backtest} />

          {data.comparison && data.comparison.length > 0 && (
            <div data-testid="forecast-comparison">
              <h3 className="text-sm font-semibold">{t("fc.comparison")}</h3>
              <ul className="mt-1 space-y-1 text-xs text-slate-300">
                {data.comparison.map((c) => {
                  const l = validSteps(c.steps).slice(-1)[0];
                  const b80 = BANDS.find((b) => b.level === 80)!;
                  return (
                    <li key={c.method_key}>{t("fc.comparisonLine", { name: c.name, range: l ? t("fc.rangeTo", { a: money(l.quantiles[b80.lower], currency), b: money(l.quantiles[b80.upper], currency) }) : t("common.unavailable") })}
                      <details className="mt-1"><summary className="cursor-pointer text-slate-400">{t("fc.comparisonBacktest")}</summary><div className="mt-1"><ForecastBacktestBlock b={c.backtest ?? null} /></div></details>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          {data.data_basis && <div className="flex flex-wrap gap-2">{data.data_basis.sources.map((s) => <SourceTip key={s.key} source={s} fetchedAt={data.data_basis!.last_fetched_at} />)}</div>}
        </div>
      )}
    </section>
  );
}
