import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { NewsClusterCard } from "../components/NewsClusterCard";
import { EventList, MoveList, PatternList, ZoneList } from "../components/AnalysisLists";
import { ForecastPanel } from "../components/ForecastPanel";
import { PatternPanel } from "../components/PatternPanel";
import { PriceChart, type ChartKind, type NewsMarker, type PriceOverlay } from "../components/PriceChart";
import { SourceTip } from "../components/SourceTip";
import { SectionNav } from "../components/SectionNav";
import { Skeleton } from "../components/Skeleton";
import { SubChart } from "../components/SubChart";
import { useLiveEvents } from "../hooks/useLiveEvents";
import { INDICATOR_TOGGLES, patternTimeframe, useIndicatorEvents, useIndicators, useMoveLinks, usePatterns } from "../lib/analysis";
import { forecastTimeframe, scenarioLevels, useForecast, validSteps } from "../lib/forecast";
import { alignSeries, toTime } from "../lib/chartData";
import { ChartGroup } from "../lib/chartSync";
import { api, PENDING_POLL_MS, type BarsResponse, type InstrumentWithQuote } from "../lib/api";
import { formatDateTime, formatPercent, formatPrice } from "../lib/format";
import { useI18n, type MessageKey } from "../lib/i18n";
import { useInstrumentNews } from "../lib/news";
import { RANGES, rangeStart, windowBars } from "../lib/timeframes";

export function ChartPage() {
  const { t } = useI18n();
  const rangeName = (label: string) => t(`range.${label}` as MessageKey);
  const { id } = useParams();
  const qc = useQueryClient();
  const [rangeLabel, setRangeLabel] = useState("6M");
  const [kind, setKind] = useState<ChartKind>("candles");
  const range = RANGES.find((r) => r.label === rangeLabel) ?? RANGES[3];
  const intraday = range.timeframe !== "1d";

  const inst = useQuery({ queryKey: ["instrument", id], queryFn: () => api<InstrumentWithQuote>(`/instruments/${id}`), refetchInterval: 15_000 });
  const bars = useQuery({
    queryKey: ["bars", id, range.label],
    queryFn: () => api<BarsResponse>(`/instruments/${id}/bars?timeframe=${range.timeframe}&start=${encodeURIComponent(rangeStart(range))}`),
    refetchInterval: (q) => (q.state.data?.pending ? PENDING_POLL_MS : intraday ? 15_000 : 60_000),
  });
  useLiveEvents((e) => {
    if (e.type === "detection" && String(e.payload.instrument_id) === id) {
      qc.invalidateQueries({ queryKey: e.payload.category === "indicator_event" ? ["indicator-events", id] : ["patterns", id] });
    }
    if (e.type === "quote" && String(e.payload.instrument_id) === id) {
      qc.invalidateQueries({ queryKey: ["instrument", id] });
      qc.invalidateQueries({ queryKey: ["bars", id] });
    }
  });

  const [selected, setSelected] = useState<number[]>([]);
  const firstBar = bars.data?.bars[0]?.ts_utc;
  const news = useInstrumentNews(id, firstBar ? firstBar.slice(0, 13) + ":00:00Z" : undefined);
  const shown = useMemo(() => windowBars(bars.data?.bars ?? [], range), [bars.data, range]);
  const markers = useMemo<NewsMarker[]>(() => {
    if (shown.length === 0) return [];
    const from = new Date(shown[0].ts_utc).getTime();
    return (news.data?.items ?? [])
      .filter((c) => new Date(c.first_published_at).getTime() >= from)
      .map((c) => ({ clusterId: c.id, ts: c.first_published_at, title: c.canonical_title }));
  }, [news.data, shown]);
  const selectedClusters = (news.data?.items ?? []).filter((c) => selected.includes(c.id));

  // Phase 3: Indikatoren, Muster, Ereignisse, Bewegungen mit zeitlich passenden Meldungen.
  const startIso = shown[0]?.ts_utc;
  const [activeInd, setActiveInd] = useState<string[]>([]);
  const [selectedPattern, setSelectedPattern] = useState<number | null>(null);
  const [showInvalid, setShowInvalid] = useState(false);
  const group = useMemo(() => new ChartGroup(), []);
  const ind = useIndicators(id, range.timeframe, startIso, activeInd);
  const events = useIndicatorEvents(id, range.timeframe, startIso);
  const moves = useMoveLinks(id, range.timeframe, startIso);
  const patTf = patternTimeframe(range.timeframe);
  const patterns = usePatterns(id, patTf, startIso, showInvalid);
  const detections = patterns.data?.detections ?? [];
  const selectedDetection = detections.find((d) => d.id === selectedPattern) ?? null;
  const [showForecast, setShowForecast] = useState(true);
  const [showMedian, setShowMedian] = useState(true);
  const [showExamples, setShowExamples] = useState(false);
  const [horizon, setHorizon] = useState(20);
  const fcTf = forecastTimeframe(range.timeframe);
  const forecast = useForecast(id, fcTf, horizon, showForecast);
  const forecastSteps = useMemo(() => validSteps(forecast.data?.steps ?? []), [forecast.data]);
  const levels = useMemo(() => scenarioLevels(selectedDetection), [selectedDetection]);
  const toggleInd = (key: string) => setActiveInd((a) => (a.includes(key) ? a.filter((k) => k !== key) : [...a, key]));
  const overlays = useMemo<PriceOverlay[]>(() => {
    if (!ind.data || shown.length === 0) return [];
    const barTimes = shown.map((b) => toTime(b.ts_utc));
    const colors: Record<string, string> = { sma: "#facc15", ema: "#fb923c", bollinger: "#94a3b8" };
    const out: PriceOverlay[] = [];
    ind.data.indicators.filter((i) => i.panel === "price" && activeInd.length > 0).forEach((i, n) => {
      const line = (name: keyof typeof i.lines, dashed = false) => out.push({ id: `${i.key}-${name}`, color: colors[i.type] ?? "#e2e8f0", dashed: dashed || i.type === "ema" && n % 2 === 1,
        data: alignSeries(ind.data!.timestamps, i.lines[name], barTimes) });
      if (i.type === "bollinger") { line("upper", true); line("middle"); line("lower", true); } else line("value");
    });
    return out;
  }, [ind.data, shown, activeInd]);
  const ownPanels = (ind.data?.indicators ?? []).filter((i) => i.panel === "own" && activeInd.length > 0);
  const q = inst.data?.quote;
  const last = shown[shown.length - 1];
  const lastUpdate = bars.dataUpdatedAt ? new Date(bars.dataUpdatedAt).toISOString() : null;

  return (
    <section>
      <Link to="/" className="inline-flex min-h-[40px] items-center text-sm text-slate-400 hover:text-slate-200">{t("chart.back")}</Link>
      {inst.isError && <p role="alert" className="mt-2 text-rose-300">{t("chart.instrumentError")}</p>}
      {inst.isLoading && <div className="mb-4 space-y-2"><Skeleton className="h-7 w-1/2" /><Skeleton className="h-9 w-40" /></div>}
      {inst.data && (
        <header className="mb-3">
          <h1>{inst.data.symbol} <span className="font-normal text-slate-400">{inst.data.name} · {inst.data.exchange}</span></h1>
          {q ? (
            <div>
              <p className="text-2xl font-semibold">{formatPrice(q.price, inst.data.currency)}
                {q.change_pct != null && <span className={`ml-2 text-base ${q.change_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{formatPercent(q.change_pct / 100)}</span>}
              </p>
              <SourceTip source={q.source} ts={q.ts_utc} fetchedAt={q.fetched_at} />
            </div>
          ) : (
            <p className="text-sm text-amber-300">{t("chart.noQuote")}</p>
          )}
        </header>
      )}

      <SectionNav items={[
        { id: "sec-chart", label: t("chart.sec.chart") },
        { id: "sec-muster", label: t("chart.sec.patterns"), count: detections.length },
        { id: "sec-prognose", label: t("chart.sec.forecast") },
        { id: "sec-ereignisse", label: t("chart.sec.events"), count: events.data?.events.length },
        { id: "sec-bewegungen", label: t("chart.sec.moves"), count: moves.data?.moves.length },
        { id: "sec-nachrichten", label: t("chart.sec.news"), count: markers.length },
      ]} />

      <div id="sec-chart" className="scroll-mt-28">
      <div className="card mb-3 space-y-3 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label={t("chart.period")} className="flex flex-wrap gap-1">
            {RANGES.map((r) => (
              <button key={r.label} type="button" aria-pressed={r.label === rangeLabel} onClick={() => setRangeLabel(r.label)}
                className={`seg ${r.label === rangeLabel ? "seg-on" : ""}`}>{rangeName(r.label)}</button>
            ))}
          </div>
          <div role="group" aria-label={t("chart.type")} className="ml-auto flex gap-1">
            {(["candles", "line"] as const).map((k) => (
              <button key={k} type="button" aria-pressed={k === kind} onClick={() => setKind(k)}
                className={`seg ${k === kind ? "seg-on" : ""}`}>{t(k === "candles" ? "chart.candles" : "chart.line")}</button>
            ))}
          </div>
        </div>
        <div role="group" aria-label={t("chart.indicators")} className="-mx-1 flex items-center gap-2 overflow-x-auto px-1 pb-1" data-testid="indicator-toggles">
          <span className="shrink-0 text-sm text-slate-400">{t("chart.indicatorsLabel")}</span>
          {INDICATOR_TOGGLES.map((tg) => (
            <label key={tg.key} className={`seg shrink-0 cursor-pointer ${activeInd.includes(tg.key) ? "seg-on" : ""}`}>
              <input type="checkbox" className="sr-only" checked={activeInd.includes(tg.key)} onChange={() => toggleInd(tg.key)} />{tg.labelKey ? t(tg.labelKey) : tg.label}
            </label>
          ))}
          <span className="mx-1 h-5 w-px shrink-0 bg-slate-700" aria-hidden="true" />
          <label className={`seg shrink-0 cursor-pointer ${showForecast ? "seg-on" : ""}`}>
            <input type="checkbox" className="sr-only" checked={showForecast} onChange={() => setShowForecast((v) => !v)} />{t("chart.forecastToggle")}
          </label>
          {showForecast && fcTf != null && (<>
            <label className={`seg shrink-0 cursor-pointer ${showMedian ? "seg-on" : ""}`} title={t("chart.medianTitle")}>
              <input type="checkbox" className="sr-only" checked={showMedian} onChange={() => setShowMedian((v) => !v)} />{t("chart.medianToggle")}
            </label>
            <label className={`seg shrink-0 cursor-pointer ${showExamples ? "seg-on" : ""}`} title={t("chart.examplesTitle")}>
              <input type="checkbox" className="sr-only" checked={showExamples} onChange={() => setShowExamples((v) => !v)} />{t("chart.examplesToggle")}
            </label>
          </>)}
        </div>
      </div>

      {bars.isLoading && <div role="status" aria-label={t("chart.loadingBars")}><Skeleton className="h-72 w-full sm:h-96" /><p className="mt-2 text-sm text-slate-400">{t("chart.loadingBars")}</p></div>}
      {bars.isError && <p role="alert" className="text-rose-300">{t("chart.barsError")}</p>}
      {bars.data && shown.length === 0 && bars.data.pending && (
        <div className="rounded border border-slate-700 bg-slate-900 p-4 text-slate-200" data-testid="bars-pending" role="status">
          <p className="font-semibold">{t("chart.barsPending")}</p>
          <p className="text-sm text-slate-400">{bars.data.empty_reason}</p>
        </div>
      )}
      {bars.data && shown.length === 0 && !bars.data.pending && (
        <div className="rounded border border-amber-700/50 bg-amber-950/30 p-4 text-amber-200" data-testid="no-bars">
          <p className="font-semibold">{t("chart.noBars")}</p>
          <p className="text-sm">{bars.data.empty_reason ?? t("chart.noBarsHint")}</p>
        </div>
      )}
      {shown.length > 0 && (
        <>
          <PriceChart bars={shown} kind={kind} intraday={intraday} markers={markers} onMarkerClick={setSelected}
            overlays={overlays} patterns={detections} zones={patterns.data?.zones ?? []} events={events.data?.events ?? []}
            selectedPatternId={selectedPattern} onPatternClick={setSelectedPattern} group={group}
            forecast={showForecast ? forecastSteps : []} scenarioLevels={showForecast ? levels : []}
            medianLine={showForecast && showMedian} examplePaths={showForecast && showExamples ? forecast.data?.example_paths ?? [] : []} />
          {ownPanels.map((i) => (
            <div key={i.key} className="mt-2">
              <p className="text-xs text-slate-400">{i.label}</p>
              <SubChart series={i} timestamps={ind.data!.timestamps} bars={shown} intraday={intraday} group={group} />
            </div>
          ))}
          {activeInd.length > 0 && (
            <div className="mt-2 text-xs text-slate-400" data-testid="indicator-info">
              {ind.isLoading && <p>{t("chart.loadingInd")}</p>}
              {ind.isError && <p role="alert" className="text-rose-300">{t("chart.indError")}</p>}
              {ind.data?.empty_reason && <p className="text-amber-300" data-testid="no-indicators">{t("chart.noInd", { reason: ind.data.empty_reason })}</p>}
              {ind.data && !ind.data.empty_reason && (
                <>
                  <p>{t("chart.indBasis", { plural: ind.data.sources.length === 1 ? "" : t("chart.indBasisPlural"), sources: ind.data.sources.map((s) => s.name).join(", "), algo: ind.data.algo_version, time: ind.data.bars_fetched_at ? formatDateTime(ind.data.bars_fetched_at) : t("chart.timeNA") })}</p>
                  <ul className="mt-1 list-disc pl-5">{ind.data.indicators.map((i) => <li key={i.key}>{i.label}{i.formula ? `: ${i.formula}` : ""}</li>)}</ul>
                  {activeInd.some((k) => !ind.data!.indicators.some((i) => i.key === INDICATOR_TOGGLES.find((tg) => tg.key === k)?.seriesKey)) && <p className="text-amber-300">{t("chart.indMissing")}</p>}
                  <div className="mt-1 flex flex-wrap gap-2">{ind.data.sources.map((s) => <SourceTip key={s.key} source={s} fetchedAt={ind.data!.bars_fetched_at ?? ""} />)}</div>
                </>
              )}
            </div>
          )}
          <p className="mt-2 text-xs text-slate-400" data-testid="last-update">
            {t("chart.lastPoint", { time: last ? formatDateTime(last.ts_utc) : "" })}
            {lastUpdate && t("chart.lastUpdate", { time: formatDateTime(lastUpdate) })}
            {shown.some((b) => b.is_demo) && ` · ${t("demo.data")}`}
          </p>
          {last && <SourceTip source={last.source} ts={last.ts_utc} fetchedAt={last.fetched_at} />}
        </>
      )}

      </div>

      <div id="sec-muster" className="card scroll-mt-28 mt-6" data-testid="chart-patterns">
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h2 className="section-title">{t("chart.patterns")}</h2>
          <label className="text-xs text-slate-300"><input type="checkbox" checked={showInvalid} onChange={(e) => setShowInvalid(e.target.checked)} /> {t("chart.showInvalid")}</label>
        </div>
        {patTf == null && <p className="text-sm text-amber-300" data-testid="no-patterns">{t("chart.patternTf", { range: rangeName(range.label), tf: range.timeframe })}</p>}
        {patterns.isError && <p role="alert" className="text-rose-300">{t("chart.patternsError")}</p>}
        {patterns.data?.pending && <p className="text-sm text-slate-300" role="status" data-testid="patterns-pending">{t("chart.patternsPending", { reason: patterns.data.empty_reason ?? "" })}</p>}
        {patterns.data?.empty_reason && !patterns.data.pending && <p className="text-sm text-amber-300" data-testid="no-patterns">{t("chart.noPatterns", { reason: patterns.data.empty_reason ?? "" })}</p>}
        {detections.length > 0 && <PatternList items={detections} selectedId={selectedPattern} onSelect={setSelectedPattern} />}
        {patterns.data && <ZoneList zones={patterns.data.zones} />}
        {selectedDetection && <div className="mt-4"><PatternPanel p={selectedDetection} onClose={() => setSelectedPattern(null)} /></div>}
        {detections.length > 0 && !selectedDetection && <p className="mt-2 text-xs text-slate-400">{t("chart.pickPattern")}</p>}
      </div>

      {showForecast && (
        <div id="sec-prognose" className="scroll-mt-28 mt-6" data-testid="chart-forecast">
          {fcTf == null
            ? <p className="text-sm text-amber-300" data-testid="no-forecast">{t("chart.forecastDaily", { range: rangeName(range.label), tf: range.timeframe })}</p>
            : <ForecastPanel data={forecast.data} loading={forecast.isLoading} error={forecast.isError} horizon={horizon} onHorizon={setHorizon} currency={inst.data?.currency ?? "EUR"} pattern={selectedDetection} showMedian={showMedian} showExamples={showExamples} />}
        </div>
      )}

      <div id="sec-ereignisse" className="card scroll-mt-28 mt-6" data-testid="chart-events">
        <h2 className="section-title mb-2">{t("chart.events")}</h2>
        {events.isError && <p role="alert" className="text-rose-300">{t("chart.eventsError")}</p>}
        {events.data?.empty_reason && <p className="text-sm text-amber-300" data-testid="no-events">{t("chart.noEvents", { reason: events.data.empty_reason ?? "" })}</p>}
        {events.data && events.data.events.length > 0 && <><p className="mb-2 text-xs text-slate-400">{t("chart.eventsLegend")}</p><EventList events={events.data.events} /></>}
      </div>

      <div id="sec-bewegungen" className="card scroll-mt-28 mt-6" data-testid="chart-moves">
        <h2 className="section-title mb-2">{t("chart.moves")}</h2>
        {moves.isError && <p role="alert" className="text-rose-300">{t("chart.movesError")}</p>}
        {moves.data?.empty_reason && <p className="text-sm text-amber-300" data-testid="no-moves">{t("chart.noMoves", { reason: moves.data.empty_reason ?? "" })}</p>}
        {moves.data && moves.data.moves.length > 0 && <MoveList moves={moves.data.moves} note={moves.data.note} onOpenNews={(cid) => setSelected([cid])} />}
      </div>

      <div id="sec-nachrichten" className="card scroll-mt-28 mt-6" data-testid="chart-news">
        <h2 className="section-title mb-2">{t("chart.newsMarkers")}</h2>
        {news.isError && <p role="alert" className="text-rose-300">{t("chart.newsError")}</p>}
        {news.data?.empty_reason && <p className="text-sm text-amber-300" data-testid="no-markers">{t("chart.noMarkers", { reason: news.data.empty_reason ?? "" })}</p>}
        {news.data && !news.data.empty_reason && markers.length === 0 && <p className="text-sm text-slate-400">{t("chart.noNewsInRange")}</p>}
        {markers.length > 0 && <p className="text-xs text-slate-400">{t("chart.markerHelp")}</p>}
        <div className="mt-3 space-y-4">{selectedClusters.map((c) => <NewsClusterCard key={c.id} cluster={c} />)}</div>
      </div>
    </section>
  );
}
