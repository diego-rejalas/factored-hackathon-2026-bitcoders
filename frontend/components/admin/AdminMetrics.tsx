"use client";

import { useCallback, useEffect, useState } from "react";
import { reasonLabel, tr } from "@/lib/i18n";
import type { AgentMetrics, BackendMetrics, DataFreshness } from "@/lib/types";
import { formatDate } from "@/lib/types";

type FetchError = Error & { status?: number };

export default function AdminMetrics({
  agentUrl,
  token,
  onSessionExpired,
}: {
  agentUrl: string;
  token: string;
  onSessionExpired: () => void;
}) {
  const [backend, setBackend] = useState<BackendMetrics | null>(null);
  const [agent, setAgent] = useState<AgentMetrics | null>(null);
  const [freshness, setFreshness] = useState<DataFreshness | null>(null);
  const [errors, setErrors] = useState({ backend: false, agent: false, freshness: false });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setErrors({ backend: false, agent: false, freshness: false });
    const paths = ["/admin/metrics", "/admin/agent-metrics", "/meta/data"];
    const results = await Promise.allSettled(paths.map(async (path) => {
      const response = await fetch(`${agentUrl}${path}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (response.status === 401) {
        const error = new Error("session") as FetchError;
        error.status = 401;
        throw error;
      }
      if (!response.ok) {
        const error = new Error(`request ${response.status}`) as FetchError;
        error.status = response.status;
        throw error;
      }
      return response.json();
    }));

    if (results.some((result) => result.status === "rejected" && (result.reason as FetchError)?.status === 401)) {
      onSessionExpired();
      return;
    }
    const nextErrors = { backend: false, agent: false, freshness: false };
    if (results[0].status === "fulfilled") setBackend(results[0].value as BackendMetrics);
    else nextErrors.backend = true;
    if (results[1].status === "fulfilled") setAgent(results[1].value as AgentMetrics);
    else nextErrors.agent = true;
    if (results[2].status === "fulfilled") setFreshness(results[2].value as DataFreshness);
    else nextErrors.freshness = true;
    setErrors(nextErrors);
    setLoading(false);
  }, [agentUrl, onSessionExpired, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const safe = backend?.safe_automated_resolution;
  const escalations = backend?.escalations;
  const containment = agent?.containment;
  const verifyTotal = (agent?.verify?.ok ?? 0) + (agent?.verify?.failed ?? 0);
  const verifyPercent = verifyTotal ? (100 * (agent?.verify?.ok ?? 0)) / verifyTotal : null;

  return (
    <section className="metrics-view" aria-labelledby="metrics-title">
      <div className="view-heading">
        <div>
          <span className="eyebrow">Calidad, operación y datos</span>
          <h2 id="metrics-title">{tr("es", "metrics")}</h2>
          <p>Las tasas incluyen su numerador y denominador; sin muestra, el valor queda sin definir.</p>
        </div>
        <button className="btn-ghost" type="button" onClick={() => void load()} disabled={loading}>
          {tr("es", "refresh")}
        </button>
      </div>

      {loading ? (
        <div className="metrics-skeletons" aria-label={tr("es", "loading")}>
          <div className="skeleton" /><div className="skeleton" /><div className="skeleton" />
        </div>
      ) : (
        <>
          <div className="kpis">
            <Kpi label={tr("es", "cases")} value={backend ? String(backend.total_cases) : tr("es", "notDefined")} />
            <Kpi
              label={tr("es", "safeResolution")}
              value={percent(safe?.rate_percent)}
              denominator={safe ? `${safe.resolved} / ${safe.attempted} casos` : tr("es", "notDefined")}
              tone="ok"
            />
            <Kpi
              label={tr("es", "escalations")}
              value={percent(escalations?.rate_percent)}
              denominator={escalations && backend ? `${escalations.count} / ${backend.total_cases} casos` : tr("es", "notDefined")}
              tone="danger"
            />
            <Kpi
              label={tr("es", "humanClosed")}
              value={backend ? String(backend.human_closure.closed) : tr("es", "notDefined")}
              denominator={backend ? `${backend.human_closure.closed} casos` : undefined}
            />
            <Kpi
              label={tr("es", "containment")}
              value={percent(containment?.rate_percent)}
              denominator={containment ? `${containment.without_transfer} / ${containment.conversations} conversaciones` : tr("es", "notDefined")}
              tone="primary"
            />
            <Kpi
              label={tr("es", "runs")}
              value={agent?.tracing_enabled ? String(agent.total_runs ?? 0) : tr("es", "notDefined")}
              denominator={agent?.tracing_enabled ? Object.entries(agent.runs_by_outcome ?? {}).map(([key, count]) => `${labelFor(key)}: ${count}`).join(" · ") : tr("es", "tracingOff")}
            />
            <Kpi
              label={tr("es", "verifySuccess")}
              value={percent(verifyPercent)}
              denominator={verifyTotal ? `${agent?.verify?.ok ?? 0} / ${verifyTotal} verificaciones` : tr("es", "notDefined")}
              tone="ok"
            />
          </div>

          <div className="metrics-grid">
            <section className="panel">
              <h3>{tr("es", "byStatus")}</h3>
              {errors.backend ? <PanelError /> : backend ? (
                <CountBars values={backend.by_status} />
              ) : <p className="empty">{tr("es", "notDefined")}</p>}
            </section>
            <section className="panel">
              <h3>{tr("es", "byLanguage")} <span className="sub">backend / casos con handoff</span></h3>
              {errors.backend ? <PanelError /> : backend ? (
                <CountBars values={Object.fromEntries(backend.by_language.map((row) => [languageName(row.language), row.n]))} />
              ) : <p className="empty">{tr("es", "notDefined")}</p>}
            </section>
            <section className="panel">
              <h3>{tr("es", "byReason")}</h3>
              {errors.backend ? <PanelError /> : backend ? (
                <CountBars values={Object.fromEntries(backend.by_reason.map((row) => [reasonLabel(row.reason, "es"), row.n]))} tone="danger" />
              ) : <p className="empty">{tr("es", "notDefined")}</p>}
            </section>
            <section className="panel">
              <h3>{tr("es", "intentDistribution")} <span className="sub">traza del agente</span></h3>
              {errors.agent || !agent?.tracing_enabled ? <p className="empty">{tr("es", "notDefined")}</p> : <CountBars values={agent.intents ?? {}} />}
            </section>
            <section className="panel">
              <h3>{tr("es", "agentLanguage")} <span className="sub">traza del agente</span></h3>
              {errors.agent || !agent?.tracing_enabled ? <p className="empty">{tr("es", "notDefined")}</p> : (
                <CountBars values={Object.fromEntries(Object.entries(agent.languages ?? {}).map(([key, count]) => [languageName(key), count]))} />
              )}
            </section>
            <section className="panel">
              <h3>{tr("es", "latency")}</h3>
              {errors.agent || !agent?.tracing_enabled ? <p className="empty">{tr("es", "notDefined")}</p> : (
                <div
                  className="table-wrap metrics-table-wrap"
                  role="region"
                  aria-label="Latencias por nodo, tabla desplazable"
                  tabIndex={0}
                >
                  <table className="data metrics-table">
                    <caption className="sr-only">Latencias p50 y p95 del agente por nodo, en milisegundos</caption>
                    <thead><tr><th scope="col">{tr("es", "node")}</th><th scope="col">{tr("es", "p50")} (ms)</th><th scope="col">{tr("es", "p95")} (ms)</th><th scope="col">n</th></tr></thead>
                    <tbody>
                      {Object.entries(agent.latency_by_node ?? {}).map(([node, values]) => (
                        <tr key={node}><th scope="row">{node}</th><td className="tnum">{metricNumber(values.p50_ms)}</td><td className="tnum">{metricNumber(values.p95_ms)}</td><td className="tnum">{values.n}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>

          {errors.backend && <div className="alert alert-error" role="alert">No se pudieron cargar las métricas de casos.</div>}
          {errors.agent && <div className="alert alert-info" role="status">No se pudieron cargar las métricas del agente.</div>}
          {errors.freshness ? (
            <section className="panel"><h3>{tr("es", "dataFreshness")}</h3><PanelError /></section>
          ) : freshness ? (
            <FreshnessPanel freshness={freshness} />
          ) : null}
          <p className="metric-caveat">
            Las métricas de contención son un proxy basado en conversaciones observadas. Sin etiquetas de referencia ni telemetría de costos, no se publica una tasa de resultados inseguros ni un costo por caso; un cero observado no implica riesgo cero.
          </p>
        </>
      )}
    </section>
  );
}

function Kpi({
  label,
  value,
  denominator,
  tone,
}: {
  label: string;
  value: string;
  denominator?: string;
  tone?: "ok" | "danger" | "primary";
}) {
  return (
    <article className={`kpi ${tone ? `kpi-${tone}` : ""}`}>
      <span className="label">{label}</span>
      <strong className="value tnum">{value}</strong>
      {denominator && <span className="denominator">{denominator}</span>}
    </article>
  );
}

// Spanish names for the values the backend and the agent's trace use as keys. An unknown key shows as it is.
const LABELS: Record<string, string> = {
  open: "Abierto",
  auto_resolved: "Resuelto automáticamente",
  escalated: "Escalado",
  in_progress: "En curso",
  closed: "Cerrado",
  resolved: "Resuelto",
  clarify: "Aclaración",
  declined: "Declinado",
  unavailable: "No disponible",
  dispute: "Disputa",
  case_status: "Estado de un caso",
  greeting: "Saludo",
  out_of_scope: "Fuera de alcance",
  fraud_report: "Reporte de fraude",
};

function labelFor(key: string): string {
  if (LABELS[key]) return LABELS[key];
  if (key.startsWith("llm_rejected")) return "Borrador del modelo rechazado";
  return key;
}

function CountBars({ values, tone }: { values: Record<string, number>; tone?: "danger" }) {
  const rows = Object.entries(values).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...rows.map(([, value]) => value));
  if (!rows.length) return <p className="empty">{tr("es", "notDefined")}</p>;
  return (
    <div className="bar-list">
      {rows.map(([label, value]) => (
        <div className="bar-item" key={label}>
          <span className="bar-label" title={labelFor(label)}>{labelFor(label)}</span>
          <span className="bar-track" aria-hidden="true"><span className={`bar-fill ${tone ?? ""}`} style={{ width: `${Math.max(2, (value / max) * 100)}%` }} /></span>
          <span className="count tnum">{value}</span>
        </div>
      ))}
    </div>
  );
}

function FreshnessPanel({ freshness }: { freshness: DataFreshness }) {
  const run = freshness.last_etl_run;
  const runStatus = run && typeof run.status === "string" ? run.status : tr("es", "notAvailable");
  const runId = run && typeof run.run_id === "string" ? run.run_id : tr("es", "notAvailable");
  const finishedAt = run && typeof run.finished_at === "string" ? run.finished_at : null;
  return (
    <section className="panel freshness-panel">
      <h3>{tr("es", "dataFreshness")}</h3>
      <div className="freshness">
        <div className="cell"><span className="label">{tr("es", "customers")}</span><span className="value tnum">{freshness.gold.customers.toLocaleString("es-419")}</span></div>
        <div className="cell"><span className="label">{tr("es", "transactions")}</span><span className="value tnum">{freshness.gold.transactions.toLocaleString("es-419")}</span></div>
        <div className="cell"><span className="label">{tr("es", "snapshotDate")}</span><span className="value">{formatDate(freshness.gold.snapshot_edge, "es")}</span></div>
        <div className="cell"><span className="label">{tr("es", "lastRun")}</span><span className="value"><span className={`badge badge-${runStatus === "success" ? "success" : "unknown"}`}>{runStatus}</span></span></div>
        <div className="cell"><span className="label">Ejecución</span><span className="value mono">{runId}</span></div>
        <div className="cell"><span className="label">Finalizada</span><span className="value">{formatDate(finishedAt, "es")}</span></div>
      </div>
      <p className="freshness-note">El dataset es un snapshot estático; la fecha refleja su borde temporal, no la hora actual.</p>
    </section>
  );
}

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? tr("es", "notDefined") : `${value.toFixed(1)}%`;
}

function metricNumber(value: number | null): string {
  return value === null ? tr("es", "notDefined") : value.toFixed(1);
}

function languageName(language: string): string {
  if (language === "es") return "Español";
  if (language === "pt") return "Português";
  if (language === "unknown") return "No identificado";
  return language;
}

function PanelError() {
  return <div className="alert alert-error">No se pudo cargar esta sección. Actualiza las métricas.</div>;
}
