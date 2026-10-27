import { CardSkeleton } from "../components/Skeleton";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLiveEvents } from "../hooks/useLiveEvents";
import { api, type Source } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useI18n, type MessageKey } from "../lib/i18n";

const STATUS: Record<Source["status"], string> = {
  online: "border-emerald-600 text-emerald-300",
  degraded: "border-amber-600 text-amber-300",
  offline: "border-rose-600 text-rose-300",
  disabled: "border-slate-600 text-slate-300",
};
const KINDS = ["price", "news", "llm", "reference"];

export function Sources() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["sources"], queryFn: () => api<Source[]>("/sources"), refetchInterval: 30_000 });
  useLiveEvents((e) => { if (e.type === "source_status") qc.invalidateQueries({ queryKey: ["sources"] }); });

  return (
    <section>
      <h1 className="mb-2">{t("sources.title")}</h1>
      <p className="mb-4 text-sm text-slate-400">{t("sources.intro")}</p>
      {q.isLoading && <div className="grid gap-4 md:grid-cols-2"><CardSkeleton /><CardSkeleton /></div>}
      {q.isError && <p role="alert" className="text-rose-300" data-testid="sources-error">{t("sources.loadError")}</p>}
      {q.data && q.data.length === 0 && <p className="text-amber-300" data-testid="no-sources">{t("sources.none")}</p>}
      <div className="grid gap-4 md:grid-cols-2">
        {q.data?.map((s) => {
          const status = STATUS[s.status] ? s.status : "offline";
          return (
            <article key={s.key} className="card" data-testid="source-card">
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-semibold"><a href={s.homepage} target="_blank" rel="noreferrer" className="underline">{s.name}</a></h2>
                <span className={`rounded border px-2 py-0.5 text-xs ${STATUS[status]}`} data-testid="source-status">{t(`sources.status.${status}` as MessageKey)}</span>
              </div>
              <p className="text-xs text-slate-400">{KINDS.includes(s.kind) ? t(`sources.kind.${s.kind}` as MessageKey) : s.kind}{t(s.is_official ? "sources.official" : "sources.unofficial")}</p>
              <p className="mt-2 text-sm">{s.description}</p>
              <dl className="mt-3 grid grid-cols-[auto,minmax(0,1fr)] [&_dd]:break-words gap-x-3 gap-y-1 text-sm">
                <dt className="text-slate-400">{t("sources.interval")}</dt><dd>{s.update_interval}</dd>
                <dt className="text-slate-400">{t("sources.delay")}</dt><dd>{s.delay_text}</dd>
                <dt className="text-slate-400">{t("sources.apiKey")}</dt><dd>{t(s.requires_key ? "sources.keyRequired" : "sources.keyNotRequired")}</dd>
                <dt className="text-slate-400">{t("sources.lastSuccess")}</dt><dd>{s.last_success_at ? formatDateTime(s.last_success_at) : t("sources.noSuccess")}</dd>
                {s.kind === "news" && (<><dt className="text-slate-400">{t("sources.items24h")}</dt><dd>{s.item_count_24h ?? t("common.unavailable")}</dd></>)}
                {s.last_error && (<><dt className="text-slate-400">{t("sources.lastError")}</dt><dd className="text-amber-300">{s.last_error}</dd></>)}
              </dl>
              <a href={s.terms_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs underline text-slate-400">{t("common.termsOfUse")}</a>
            </article>
          );
        })}
      </div>
    </section>
  );
}
