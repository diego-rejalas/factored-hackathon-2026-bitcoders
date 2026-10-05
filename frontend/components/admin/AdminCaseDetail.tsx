"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { caseStatusLabel, limitationLabel, reasonLabel, tr } from "@/lib/i18n";
import type { CaseEvent, DisputeCase, Handoff, TraceRow } from "@/lib/types";
import { formatAmount, formatDate } from "@/lib/types";

type DetailResponse = DisputeCase & {
  first_name?: string | null;
  last_name?: string | null;
  country?: string | null;
};

export default function AdminCaseDetail({
  agentUrl,
  token,
  caseId,
  onBack,
  onSessionExpired,
}: {
  agentUrl: string;
  token: string;
  caseId: string;
  onBack: () => void;
  onSessionExpired: () => void;
}) {
  const [caseData, setCaseData] = useState<DetailResponse | null>(null);
  const [trace, setTrace] = useState<TraceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [traceLoading, setTraceLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [traceError, setTraceError] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [note, setNote] = useState("");
  const [resolution, setResolution] = useState("resolved_customer");
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${agentUrl}/admin/disputes/${encodeURIComponent(caseId)}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (response.status === 404) throw new Error("not-found");
      if (!response.ok) throw new Error("request");
      const body = (await response.json()) as DetailResponse;
      setCaseData(body);
      setTrace([]);
      setTraceError(false);
      if (body.conversation_id) {
        setTraceLoading(true);
        try {
          const traceResponse = await fetch(
            `${agentUrl}/admin/conversations/${encodeURIComponent(body.conversation_id)}/trace`,
            { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
          );
          if (traceResponse.status === 401) {
            onSessionExpired();
            return;
          }
          if (!traceResponse.ok) throw new Error("trace");
          const traceBody = await traceResponse.json();
          setTrace(traceBody.rows ?? []);
        } catch {
          setTraceError(true);
        } finally {
          setTraceLoading(false);
        }
      }
    } catch (cause) {
      setError(cause instanceof Error && cause.message === "not-found" ? tr("es", "caseNotFound") : tr("es", "connectError"));
    } finally {
      setLoading(false);
    }
  }, [agentUrl, caseId, onSessionExpired, token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function transition(event: FormEvent<HTMLFormElement>, action: "claim" | "close") {
    event.preventDefault();
    if (actionBusy || !note.trim()) return;
    if (action === "close" && !window.confirm(tr("es", "confirmClosePrompt"))) return;
    setActionBusy(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(
        `${agentUrl}/admin/disputes/${encodeURIComponent(caseId)}/transition`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            action,
            note: note.trim(),
            ...(action === "close" ? { resolution } : {}),
          }),
        },
      );
      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (response.status === 409) {
        await load();
        setError(action === "claim" ? tr("es", "claimError") : tr("es", "transitionError"));
        return;
      }
      if (!response.ok) throw new Error("transition");
      setNotice(action === "claim" ? tr("es", "claimSuccess") : tr("es", "saved"));
      setNote("");
      await load();
    } catch {
      setError(tr("es", "transitionError"));
    } finally {
      setActionBusy(false);
    }
  }

  if (loading && !caseData) {
    return (
      <section className="case-loading" aria-label={tr("es", "loading")}>
        <button className="backlink" type="button" onClick={onBack}>← {tr("es", "inbox")}</button>
        <div className="skeleton" />
        <div className="skeleton" />
      </section>
    );
  }
  if (error && !caseData) {
    return (
      <section className="case-loading">
        <button className="backlink" type="button" onClick={onBack}>← {tr("es", "inbox")}</button>
        <div className="alert alert-error" role="alert">{error}</div>
        <button className="btn-ghost" type="button" onClick={() => void load()}>{tr("es", "retry")}</button>
      </section>
    );
  }
  if (!caseData) return null;

  const handoff = caseData.handoff ?? getHandoff(caseData.evidence);
  const isClaimable = caseData.status === "escalated" || caseData.status === "open";
  const isClosable = caseData.status === "in_progress";
  const request = handoff?.customer_language === "pt" ? handoff.request?.pt : handoff?.request?.es;
  const customerName = [caseData.first_name, caseData.last_name].filter(Boolean).join(" ") || caseData.customer_id;

  return (
    <section className="case-detail" aria-labelledby="case-detail-title">
      <button className="backlink" type="button" onClick={onBack}>← {tr("es", "inbox")}</button>
      <header className="case-hero">
        <div>
          <span className="eyebrow">{tr("es", "details")}</span>
          <h2 id="case-detail-title" className="mono">{caseData.case_id}</h2>
          <p>
            {customerName}{caseData.country ? ` · ${caseData.country}` : ""}
            {handoff?.customer_language ? <span className="language-chip">{handoff.customer_language.toUpperCase()}</span> : null}
          </p>
        </div>
        <span className={`badge badge-${caseData.status}`}>{caseStatusLabel(caseData.status, "es")}</span>
      </header>

      {notice && <div className="alert alert-success" role="status">{notice}</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}

      <section className="panel case-facts" aria-label="Resumen del caso">
        <h3>Resumen</h3>
        <dl className="case-fact-grid">
          <div><dt>{tr("es", "transaction")}</dt><dd className="mono">{caseData.transaction_id || tr("es", "unlinkedTransaction")}</dd></div>
          <div><dt>{tr("es", "reason")}</dt><dd>{reasonLabel(handoff?.reason, "es")}</dd></div>
          <div><dt>{tr("es", "created")}</dt><dd>{formatDate(caseData.created_at, "es")}</dd></div>
          <div>
            <dt>Fecha de cierre</dt>
            <dd>{caseData.status === "closed" || caseData.status === "auto_resolved" ? formatDate(caseData.resolved_at, "es") : "Pendiente"}</dd>
          </div>
        </dl>
        {caseData.summary && <p className="case-summary">{caseData.summary}</p>}
      </section>

      {handoff && (
        <section className="panel">
          <h3>{tr("es", "handoff")}</h3>
          <div className="handoff-detail">
            <section>
              <h4>{tr("es", "reason")} / {tr("es", "limitation")}</h4>
              <dl className="kv">
                <dt>Motivo</dt><dd>{reasonLabel(handoff.reason, "es")}</dd>
                <dt>{tr("es", "limitation")}</dt><dd>{limitationLabel(handoff.reason, handoff.limitation)}</dd>
              </dl>
            </section>
            {handoff.customer_message && <section><h4>Mensaje del cliente</h4><p>{handoff.customer_message}</p></section>}
            {request && <section><h4>Qué se le explicó al cliente</h4><p>{request}</p></section>}
            <ListSection title={tr("es", "verifiedFacts")} values={handoff.verified_facts} />
            <ListSection title={tr("es", "actionsTaken")} values={handoff.actions_taken?.map(actionDescription)} />
            {handoff.evidence?.length ? (
              <section>
                <h4>{tr("es", "evidence")}</h4>
                <div className="evidence-list">
                  {handoff.evidence.map((entry, index) => <EvidenceItem entry={entry} key={index} />)}
                </div>
              </section>
            ) : null}
            <ListSection title={tr("es", "openQuestions")} values={handoff.open_questions} />
          </div>
        </section>
      )}

      <section className="panel">
        <h3>{tr("es", "events")}</h3>
        {caseData.events?.length ? (
          <ol className="timeline admin-timeline">
            {caseData.events.map((event, index) => (
              <li className={index === caseData.events!.length - 1 ? "tl-accent" : ""} key={`${event.event}-${index}`}>
                <strong>{eventLabel(event)}</strong>
                {typeof event.payload?.admin === "string" && <span className="event-detail">Especialista: {event.payload.admin}</span>}
                {typeof event.payload?.note === "string" && <span className="event-detail">Nota: {event.payload.note}</span>}
                {typeof event.payload?.resolution === "string" && <span className="event-detail">Resultado: {event.payload.resolution}</span>}
                <time className="when" dateTime={event.ts || undefined}>{formatDate(event.ts, "es")}</time>
              </li>
            ))}
          </ol>
        ) : <p className="empty">{tr("es", "noEvents")}</p>}
      </section>

      <section className="panel">
        <h3>{tr("es", "trace")}</h3>
        {!caseData.conversation_id ? <p className="empty">No hay una conversación asociada a este caso.</p> : traceLoading ? (
          <div className="skeleton" />
        ) : traceError ? (
          <div className="alert alert-error" role="alert">No se pudo cargar la traza estructurada.</div>
        ) : trace.length ? (
          <ol className="timeline trace-timeline">
            {trace.map((row, index) => <TraceEvent row={row} key={`${row.node}-${index}`} />)}
          </ol>
        ) : <p className="empty">No hay eventos de traza para esta conversación.</p>}
      </section>

      {(isClaimable || isClosable) && (
        <section className="panel action-panel">
          <h3>{tr("es", "actions")}</h3>
          <form className={`transition-form ${isClosable ? "closing" : "claiming"}`} onSubmit={(event) => void transition(event, isClaimable ? "claim" : "close")}>
            <div className="field">
              <label htmlFor="transition-note">{tr("es", "note")} <span aria-hidden="true">*</span></label>
              <textarea
                id="transition-note"
                name="note"
                maxLength={2000}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder={tr("es", "notePlaceholder")}
                required
              />
            </div>
            {isClosable && (
              <div className="field">
                <label htmlFor="case-resolution">{tr("es", "resolution")}</label>
                <select id="case-resolution" value={resolution} onChange={(event) => setResolution(event.target.value)}>
                  <option value="resolved_customer">{tr("es", "resolvedCustomer")}</option>
                  <option value="no_resolution">{tr("es", "noResolution")}</option>
                </select>
              </div>
            )}
            <button className={`btn ${isClosable ? "btn-danger" : ""}`} type="submit" disabled={actionBusy || !note.trim()}>
              {actionBusy ? tr("es", "loading") : isClaimable ? tr("es", "takeCase") : tr("es", "confirmClose")}
            </button>
          </form>
        </section>
      )}
    </section>
  );
}

function getHandoff(evidence: Record<string, unknown> | undefined): Handoff | null {
  const handoff = evidence?.handoff;
  return handoff && typeof handoff === "object" ? handoff as Handoff : null;
}

function ListSection({ title, values }: { title: string; values?: string[] }) {
  if (!values?.length) return null;
  return (
    <section>
      <h4>{title}</h4>
      <ul>{values.map((value, index) => <li key={`${index}-${value}`}>{value}</li>)}</ul>
    </section>
  );
}

const ACTIONS: Record<string, string> = {
  create_dispute: "Caso registrado",
  escalate_dispute: "Caso escalado",
  resolve_dispute: "Caso resuelto automáticamente",
};

function actionDescription(action: Record<string, unknown>): string {
  const key = typeof action.action === "string" ? action.action : "";
  const name = ACTIONS[key] ?? (key ? key.replaceAll("_", " ") : "Acción");
  return action.case_id ? `${name} · #${String(action.case_id).slice(0, 8)}` : name;
}

// The agent's trace stores English keys (the metrics read them). The console shows them in Spanish.
const TRACE_NODES: Record<string, string> = {
  understand: "Entender el mensaje",
  decide: "Decidir",
  act: "Registrar el caso",
  verify: "Verificar",
  respond: "Responder",
  escalate: "Escalar a una persona",
};

const TRACE_TERMS: Record<string, string> = {
  dispute: "Disputa",
  case_status: "Estado de un caso",
  greeting: "Saludo",
  out_of_scope: "Fuera de alcance",
  fraud_report: "Reporte de fraude",
  create_dispute: "Crear caso",
  escalate_dispute: "Escalar caso",
  resolve_dispute: "Resolver caso",
  get_dispute: "Leer caso",
  check_status: "Revisar estado",
  check_amount: "Revisar monto",
  escalate: "Escalar",
  clarify: "Aclarar",
  answer: "Responder",
  act: "Actuar",
  declined: "Declinar",
  resolved: "Resuelto",
  escalated: "Escalado",
  auto_resolved: "Resuelto automáticamente",
  open: "Abierto",
  failed: "Falló",
};

function traceTerm(value: string): string {
  return TRACE_TERMS[value] ?? (value.startsWith("llm_rejected") ? "Borrador del modelo rechazado" : value);
}

function EvidenceItem({ entry }: { entry: Record<string, unknown> }) {
  const [kind, value] = Object.entries(entry)[0] ?? ["Evidencia", null];
  // Older handoffs embedded a pre-escalation copy of the dispute (always "open").
  // The current dispute and its event timeline above are authoritative.
  if (kind === "dispute") return null;
  const details = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const candidateOptions = Array.isArray(value)
    ? value
    : Array.isArray(details.candidates)
      ? details.candidates
      : [];
  const label = kind.replaceAll("_", " ");
  const effectiveAmount = details.amount_usd_effective;
  const rawAmount = details.amount;
  const currency = typeof details.currency === "string" ? details.currency : null;
  return (
    <article className="evidence-item">
      <strong>{label}</strong>
      <dl className="kv">
        {typeof details.transaction_id === "string" && <><dt>Transacción</dt><dd className="mono">{details.transaction_id}</dd></>}
        {typeof details.case_id === "string" && <><dt>Caso</dt><dd className="mono">{details.case_id}</dd></>}
        {typeof details.merchant_name === "string" && <><dt>Comercio</dt><dd>{details.merchant_name}</dd></>}
        {effectiveAmount !== null && effectiveAmount !== undefined && <><dt>Monto efectivo USD</dt><dd>{formatAmount(effectiveAmount as number | string, "es")}</dd></>}
        {(effectiveAmount === null || effectiveAmount === undefined) && rawAmount !== null && rawAmount !== undefined && <><dt>Monto original</dt><dd>{String(rawAmount)}{currency ? ` ${currency}` : ""}</dd></>}
        {typeof details.transaction_status === "string" && <><dt>Estado</dt><dd>{details.transaction_status}</dd></>}
        {typeof details.transaction_date === "string" && <><dt>Fecha</dt><dd>{formatDate(details.transaction_date, "es")}</dd></>}
        {typeof details.status === "string" && <><dt>Estado del caso</dt><dd>{details.status}</dd></>}
      </dl>
      {candidateOptions.length > 0 && (
        <ul className="candidate-option-list" aria-label="Transacciones candidatas sin selección">
          {candidateOptions.map((candidate, index) => {
            const option = candidate && typeof candidate === "object"
              ? candidate as Record<string, unknown>
              : {};
            const merchant = typeof option.merchant_name === "string" ? option.merchant_name : "Comercio no informado";
            const id = typeof option.transaction_id === "string" ? option.transaction_id : `opción ${index + 1}`;
            const amount = option.amount_usd_effective !== null && option.amount_usd_effective !== undefined
              ? formatAmount(option.amount_usd_effective as number | string, "es")
              : option.amount !== null && option.amount !== undefined
                ? `${String(option.amount)}${typeof option.currency === "string" ? ` ${option.currency}` : ""}`
                : "Monto no disponible";
            const status = typeof option.transaction_status === "string" ? option.transaction_status : "";
            return <li key={`${id}-${index}`}><span className="mono">{id}</span> · {merchant} · {amount}{status ? ` · ${status}` : ""}</li>;
          })}
        </ul>
      )}
      {typeof value === "string" && <p>{value}</p>}
    </article>
  );
}

function eventLabel(event: CaseEvent): string {
  const labels: Record<string, string> = {
    created: "Caso registrado",
    escalated: "Derivado a revisión humana",
    auto_resolved: "Resolución automática verificada",
    admin_claim: "Especialista tomó el caso",
    admin_close: "Especialista cerró el caso",
  };
  return labels[event.event] ?? event.event.replaceAll("_", " ");
}

function TraceEvent({ row }: { row: TraceRow }) {
  return (
    <li>
      <strong>{TRACE_NODES[row.node] ?? row.node}</strong>
      <span className="trace-tags">
        {row.intent && <span>{traceTerm(row.intent)}</span>}
        {row.tool && <span>{traceTerm(row.tool)}</span>}
        {row.result_status && <span>{traceTerm(row.result_status)}</span>}
        {row.latency_ms !== null && row.latency_ms !== undefined && <span className="tnum">{row.latency_ms} ms</span>}
      </span>
      <time className="when" dateTime={row.ts || undefined}>{formatDate(row.ts, "es")}</time>
    </li>
  );
}
