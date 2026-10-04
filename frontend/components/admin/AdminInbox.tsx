"use client";

import { useCallback, useEffect, useState } from "react";
import { reasonLabel, tr } from "@/lib/i18n";
import type { AdminCaseItem } from "@/lib/types";
import { formatDate } from "@/lib/types";

type StatusFilter = "active" | "all" | "escalated" | "in_progress" | "closed" | "auto_resolved";

export default function AdminInbox({
  agentUrl,
  token,
  onOpenCase,
  onSessionExpired,
}: {
  agentUrl: string;
  token: string;
  onOpenCase: (caseId: string) => void;
  onSessionExpired: () => void;
}) {
  const [filter, setFilter] = useState<StatusFilter>("active");
  const [items, setItems] = useState<AdminCaseItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const query = filter === "all" ? "" : `?status=${encodeURIComponent(filter)}`;
      const response = await fetch(`${agentUrl}/admin/disputes${query}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (!response.ok) throw new Error("load");
      const body = await response.json();
      setItems(body.items ?? []);
      setTotal(body.total ?? 0);
    } catch (cause) {
      setError(tr("es", "connectError"));
    } finally {
      setLoading(false);
    }
  }, [agentUrl, filter, onSessionExpired, token]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section aria-labelledby="inbox-title" className="inbox-view">
      <div className="view-heading">
        <div>
          <span className="eyebrow">Operación diaria</span>
          <h2 id="inbox-title">{tr("es", "inbox")}</h2>
          <p>{total} {total === 1 ? "caso" : "casos"} en el filtro seleccionado</p>
        </div>
        <div className="filterbar">
          <label htmlFor="case-status-filter">Estado</label>
          <select
            id="case-status-filter"
            value={filter}
            onChange={(event) => setFilter(event.target.value as StatusFilter)}
          >
            <option value="active">Cola activa (escalados + en curso)</option>
            <option value="escalated">{tr("es", "escalatedOnly")}</option>
            <option value="in_progress">{tr("es", "inProgressOnly")}</option>
            <option value="closed">{tr("es", "closedOnly")}</option>
            <option value="auto_resolved">Auto-resueltos</option>
            <option value="all">{tr("es", "allStatuses")}</option>
          </select>
          <button className="btn-ghost" type="button" onClick={() => void load()} disabled={loading}>
            {tr("es", "refresh")}
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
          <button className="btn-ghost retry-button" type="button" onClick={() => void load()}>
            {tr("es", "retry")}
          </button>
        </div>
      )}
      {loading ? (
        <div className="inbox-skeletons" aria-label={tr("es", "loadingInbox")}>
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      ) : !error && items.length === 0 ? (
        <div className="card empty-state">
          <span className="empty-mark" aria-hidden="true">✓</span>
          <h3>{tr("es", "emptyInbox")}</h3>
          <p>Los casos auto-resueltos no requieren intervención humana.</p>
        </div>
      ) : !error ? (
        <>
          <div
            className="table-wrap inbox-table-wrap"
            role="region"
            aria-label="Bandeja de casos desplazable"
            tabIndex={0}
          >
            <table className="data inbox-table">
              <caption className="sr-only">Casos de disputa, filtrados por estado</caption>
              <thead>
                <tr>
                  <th scope="col">{tr("es", "case")}</th>
                  <th scope="col">{tr("es", "customer")}</th>
                  <th scope="col">{tr("es", "reason")}</th>
                  <th scope="col">{tr("es", "status")}</th>
                  <th scope="col">{tr("es", "created")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.case_id}>
                    <td>
                      <button className="case-open-link mono" type="button" onClick={() => onOpenCase(item.case_id)}>
                        {item.case_id.slice(0, 8)}…
                      </button>
                      <span className="table-sub mono">{item.transaction_id || tr("es", "unlinkedTransaction")}</span>
                    </td>
                    <td>
                      <strong>{[item.first_name, item.last_name].filter(Boolean).join(" ") || item.customer_id}</strong>
                      <span className="table-sub">{item.country || item.customer_id}</span>
                      {item.customer_language && <span className="language-chip">{item.customer_language.toUpperCase()}</span>}
                    </td>
                    <td>{reasonLabel(item.handoff_reason, "es")}</td>
                    <td><span className={`badge badge-${item.status}`}>{item.status}</span></td>
                    <td className="tnum">{formatDate(item.created_at, "es")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="inbox-cards">
            {items.map((item) => (
              <button className="inbox-card" type="button" key={item.case_id} onClick={() => onOpenCase(item.case_id)}>
                <span className="inbox-card-top">
                  <span className="mono">{item.case_id.slice(0, 8)}…</span>
                  <span className={`badge badge-${item.status}`}>{item.status}</span>
                </span>
                <strong>{[item.first_name, item.last_name].filter(Boolean).join(" ") || item.customer_id}</strong>
                <span className="inbox-card-reason">{reasonLabel(item.handoff_reason, "es")}</span>
                <span className="table-sub">
                  {item.country || item.customer_id}
                  {item.customer_language ? ` · ${item.customer_language.toUpperCase()}` : ""}
                  {` · ${formatDate(item.created_at, "es")}`}
                </span>
              </button>
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
