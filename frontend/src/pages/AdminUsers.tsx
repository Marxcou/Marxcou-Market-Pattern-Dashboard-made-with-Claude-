import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, ApiError, type AdminUser } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useI18n, tr } from "../lib/i18n";
import { formatDateTime } from "../lib/format";

interface Shown { email: string; password: string }

function errText(err: unknown): string {
  return err instanceof ApiError && err.detail ? err.detail : tr("admin.failed");
}

export function AdminUsers() {
  const qc = useQueryClient();
  const { me } = useAuth();
  const { t } = useI18n();
  const q = useQuery({ queryKey: ["admin-users"], queryFn: () => api<AdminUser[]>("/users") });
  const [shown, setShown] = useState<Shown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ email: "", display_name: "", role: "user" });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-users"] });

  const create = useMutation({
    mutationFn: () => api<AdminUser & { temporary_password: string }>("/users", { method: "POST", body: JSON.stringify(form) }),
    onSuccess: (u) => { setShown({ email: u.email, password: u.temporary_password }); setForm({ email: "", display_name: "", role: "user" }); setError(null); void refresh(); },
    onError: (e) => setError(errText(e)),
  });
  const setActive = useMutation({
    mutationFn: (v: { id: number; is_active: boolean }) => api<AdminUser>(`/users/${v.id}`, { method: "PATCH", body: JSON.stringify({ is_active: v.is_active }) }),
    onSuccess: () => { setError(null); void refresh(); },
    onError: (e) => setError(errText(e)),
  });
  const reset = useMutation({
    mutationFn: (u: AdminUser) => api<{ temporary_password: string }>(`/users/${u.id}/reset-password`, { method: "POST" }).then((r) => ({ u, r })),
    onSuccess: ({ u, r }) => { setShown({ email: u.email, password: r.temporary_password }); setError(null); void refresh(); },
    onError: (e) => setError(errText(e)),
  });

  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };

  return (
    <section className="space-y-6">
      <div>
        <h1 className="mb-2 ">{t("admin.title")}</h1>
        <p className="text-sm text-slate-400">{t("admin.note")}</p>
      </div>
      {shown && (
        <div role="status" data-testid="temp-password" className="rounded border border-amber-700/50 bg-amber-950/40 p-3 text-sm text-amber-200">
          {t("admin.tempFor", { email: shown.email })} <code className="rounded bg-slate-900 px-2 py-1 text-slate-100">{shown.password}</code>
          <p className="mt-1 text-xs">{t("admin.tempNote")}</p>
          <button type="button" onClick={() => setShown(null)} className="mt-2 underline">{t("admin.hide")}</button>
        </div>
      )}
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      <form onSubmit={submit} className="grid gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4 md:grid-cols-4">
        <label className="text-sm">{t("login.email")}
          <input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
        </label>
        <label className="text-sm">{t("admin.displayName")}
          <input required maxLength={100} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
        </label>
        <label className="text-sm">{t("admin.role")}
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2">
            <option value="user">{t("admin.roleUser")}</option>
            <option value="admin">{t("admin.roleAdmin")}</option>
          </select>
        </label>
        <div className="flex items-end"><button type="submit" disabled={create.isPending} className="rounded bg-sky-700 px-4 py-2 text-sm font-semibold disabled:opacity-50">{t("admin.create")}</button></div>
      </form>
      {q.isLoading && <p className="text-slate-400">{t("admin.loading")}</p>}
      {q.isError && <p role="alert" className="text-rose-300">{t("admin.loadError")}</p>}
      {q.data && (
        <table className="w-full text-left text-sm" data-testid="user-table">
          <thead className="text-slate-400"><tr><th className="py-1">{t("admin.colName")}</th><th>{t("login.email")}</th><th>{t("admin.role")}</th><th>{t("admin.colStatus")}</th><th>{t("admin.colCreated")}</th><th /></tr></thead>
          <tbody>
            {q.data.map((u) => (
              <tr key={u.id} className="border-t border-slate-800" data-testid="user-row">
                <td className="py-2">{u.display_name}</td>
                <td>{u.email}</td>
                <td>{u.role === "admin" ? t("admin.roleAdmin") : t("admin.roleUser")}</td>
                <td>{u.is_active ? t("admin.active") : t("admin.locked")}{u.must_change_password && t("admin.pendingChange")}</td>
                <td>{formatDateTime(u.created_at)}</td>
                <td className="space-x-3 text-right">
                  {u.id !== me?.user.id && (
                    <button type="button" className="underline" onClick={() => setActive.mutate({ id: u.id, is_active: !u.is_active })}>
                      {u.is_active ? t("admin.lock") : t("admin.unlock")}
                    </button>
                  )}
                  <button type="button" className="underline" onClick={() => { if (window.confirm(t("admin.confirmReset", { email: u.email }))) reset.mutate(u); }}>
                    {t("admin.reset")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
