import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Instrument } from "../lib/api";
import { useI18n } from "../lib/i18n";

export function SearchBox({ watchedIds }: { watchedIds: Set<number> }) {
  const qc = useQueryClient();
  const { t } = useI18n();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setQ(input.trim()), 300);
    return () => clearTimeout(timer);
  }, [input]);

  const search = useQuery({
    queryKey: ["search", q],
    enabled: q.length >= 1,
    queryFn: () => api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(q)}`),
  });
  const add = useMutation({
    mutationFn: (id: number) => api("/watchlist", { method: "POST", body: JSON.stringify({ instrument_id: id }) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watchlist"] });
      // reload the counters of the new instrument (patterns, news), otherwise the card shows 0 until the next fetch
      void qc.invalidateQueries({ queryKey: ["pattern-counts"] });
      void qc.invalidateQueries({ queryKey: ["news-counts"] });
    },
  });

  return (
    <section aria-label={t("search.label")} className="mb-6">
      <label htmlFor="search" className="mb-1 block text-sm text-slate-300">{t("search.prompt")}</label>
      <input id="search" type="search" value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("search.placeholder")}
        className="min-h-[44px] w-full max-w-xl rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-base placeholder:text-slate-500" />
      {q && search.isLoading && <p className="mt-2 text-sm text-slate-400">{t("search.running")}</p>}
      {search.isError && <p className="mt-2 text-sm text-rose-300">{t("search.failed")}</p>}
      {search.data && search.data.length === 0 && (
        <p className="mt-2 text-sm text-slate-400" data-testid="no-results">{t("search.none")}</p>
      )}
      {search.data && search.data.length > 0 && (
        <ul className="mt-2 max-w-xl divide-y divide-slate-800 overflow-hidden rounded-lg border border-slate-800 bg-slate-900" data-testid="search-results">
          {search.data.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-2 px-3 py-1 text-sm">
              <Link to={`/instrument/${i.id}`} className="min-w-0 flex-1 truncate py-2">
                <span className="font-semibold">{i.symbol}</span> · {i.name} <span className="text-slate-400">({i.exchange}{i.isin ? `, ${i.isin}` : ""})</span>
              </Link>
              {watchedIds.has(i.id) ? (
                <span className="shrink-0 text-xs text-slate-400">{t("search.inWatchlist")}</span>
              ) : (
                <button type="button" className="seg shrink-0 text-xs" onClick={() => add.mutate(i.id)} disabled={add.isPending}>
                  {t("search.add")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
