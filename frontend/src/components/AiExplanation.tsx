import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDateTime, formatNumber } from "../lib/format";
import { getLang, useI18n } from "../lib/i18n";

// Erklärtext zu einer Erkennung oder Prognose (Vertrag: docs/api-contract.md, "Erklärtexte"). Der Text entsteht im
// Backend nur aus den berechneten Werten und ist je nach Herkunft als KI-Text oder als Vorlage gekennzeichnet.
export interface ExplanationResponse {
  text: string; source: "ki" | "vorlage"; label: string; model_name: string | null; model_version: string | null;
  generated_at: string; cost_usd: number; fallback_reason: string | null;
  budget: { month: string; spent_usd: number; budget_usd: number };
}

const usd = (v: number) => (getLang() === "de" ? `${formatNumber(v, v < 0.1 ? 3 : 2)} US-$` : `$${formatNumber(v, v < 0.1 ? 3 : 2)}`);

export const useExplanation = (kind: "pattern" | "forecast", id: number | undefined) =>
  useQuery({
    queryKey: ["explanation", kind, id], enabled: id != null, staleTime: 5 * 60_000, retry: false,
    queryFn: () => api<ExplanationResponse>(kind === "pattern" ? `/patterns/${id}/explanation` : `/instruments/${id}/forecast/explanation`),
  });

export function AiExplanation({ kind, id }: { kind: "pattern" | "forecast"; id: number | undefined }) {
  const { t } = useI18n();
  const q = useExplanation(kind, id);
  const e = q.data;
  const ai = e?.source === "ki";
  return (
    <section className={`mt-3 rounded border p-3 ${ai ? "border-indigo-700/60 bg-indigo-950/30" : "border-slate-700 bg-slate-950/40"}`} data-testid="ai-explanation" aria-label={t("ai.aria")} aria-busy={q.isLoading}>
      <h3 className="text-sm font-semibold">{t("ai.title")}</h3>
      {q.isLoading && <p className="mt-1 text-sm text-slate-400" role="status" data-testid="ai-explanation-loading">{t("ai.loading")}</p>}
      {q.isError && <p className="mt-1 text-sm text-slate-400" role="status" data-testid="ai-explanation-error">{t("ai.error")}</p>}
      {e && (
        <>
          <p className="mt-1 text-xs" data-testid="ai-explanation-label">
            <span className={`mr-2 rounded px-1.5 py-0.5 font-semibold ${ai ? "bg-indigo-900 text-indigo-100" : "bg-slate-800 text-slate-200"}`}>{t(ai ? "ai.badgeAi" : "ai.badgeTemplate")}</span>
            <span className="text-slate-400">
              {ai ? t("ai.created", { model: e.model_name ?? "Claude", time: formatDateTime(e.generated_at) }) : e.label}
            </span>
          </p>
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed" data-testid="ai-explanation-text">{e.text}</p>
          {e.fallback_reason && <p className="mt-2 text-xs text-amber-300" data-testid="ai-explanation-reason">{t("ai.noAi", { reason: e.fallback_reason })}</p>}
          <p className="mt-2 text-xs text-slate-400">
            {t(ai ? "ai.noteAi" : "ai.noteTemplate")}
            {ai && e.cost_usd > 0 && t("ai.cost", { cost: usd(e.cost_usd) })}
            {t("ai.monthly", { spent: usd(e.budget.spent_usd), budget: usd(e.budget.budget_usd) })}
          </p>
        </>
      )}
    </section>
  );
}
