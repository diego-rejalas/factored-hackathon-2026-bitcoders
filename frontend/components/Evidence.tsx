"use client";

import { createContext, useContext, useId } from "react";
import type { ReactNode } from "react";
import { caseStatusLabel, reasonLabel, transactionStatusLabel } from "@/lib/i18n";
import type { DisputeCase, Language } from "@/lib/types";
import { formatAmount, formatDate } from "@/lib/types";

/*
 * Evidence items: the pattern of the AI Elements "Attachments" component (a container with a layout variant,
 * an item with a preview, an info block and a hover card), without its dependencies. The items here are
 * not files: they are the verified facts a case rests on (the transaction, the decline code, what the agent
 * did), shown as the cards a customer or a specialist can scan and open.
 */

export type EvidenceVariant = "grid" | "inline" | "list";
export type EvidenceKind = "transaction" | "decision" | "handoff" | "event";

export type EvidenceData = {
  id: string;
  kind: EvidenceKind;
  title: string;
  subtitle?: string;
  details?: Array<[string, string]>;
};

const VariantContext = createContext<EvidenceVariant>("grid");

export function EvidenceList({
  variant = "grid",
  label,
  children,
}: {
  variant?: EvidenceVariant;
  label: string;
  children: ReactNode;
}) {
  return (
    <VariantContext.Provider value={variant}>
      <ul className={`ev ev-${variant}`} aria-label={label}>
        {children}
      </ul>
    </VariantContext.Provider>
  );
}

export function EvidenceItem({ data, language }: { data: EvidenceData; language: Language }) {
  const variant = useContext(VariantContext);
  const cardId = useId();
  const hasDetails = Boolean(data.details && data.details.length > 0);
  return (
    <li className={`ev-item ev-item-${variant} kind-${data.kind}`}>
      {/* The card is focusable so the hover card also opens with the keyboard and on touch. */}
      <button
        type="button"
        className="ev-trigger"
        aria-describedby={hasDetails ? cardId : undefined}
        aria-label={`${data.title}${data.subtitle ? `, ${data.subtitle}` : ""}`}
      >
        <EvidencePreview kind={data.kind} />
        <EvidenceInfo title={data.title} subtitle={data.subtitle} showSubtitle={variant !== "inline"} />
      </button>
      {hasDetails && (
        <div className="ev-hover" id={cardId} role="tooltip" lang={language}>
          <strong>{data.title}</strong>
          <dl>
            {data.details!.map(([term, value]) => (
              <div key={term}>
                <dt>{term}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </li>
  );
}

function EvidencePreview({ kind }: { kind: EvidenceKind }) {
  return (
    <span className="ev-preview" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        {kind === "transaction" && (
          <>
            <rect x="3" y="5" width="18" height="14" rx="2" />
            <path d="M3 10h18M7 15h4" />
          </>
        )}
        {kind === "decision" && (
          <>
            <circle cx="12" cy="12" r="9" />
            <path d="m8.5 12.5 2.5 2.5 4.5-5" />
          </>
        )}
        {kind === "handoff" && (
          <>
            <circle cx="9" cy="8" r="3" />
            <path d="M3.5 19c.5-3 2.7-5 5.5-5s5 2 5.5 5M16 11l2 2 3.5-4" />
          </>
        )}
        {kind === "event" && (
          <>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5l3 2" />
          </>
        )}
      </svg>
    </span>
  );
}

function EvidenceInfo({ title, subtitle, showSubtitle }: { title: string; subtitle?: string; showSubtitle: boolean }) {
  return (
    <span className="ev-info">
      <span className="ev-title">{title}</span>
      {showSubtitle && subtitle && <span className="ev-subtitle">{subtitle}</span>}
    </span>
  );
}

const TEXT = {
  es: {
    transaction: "Transacción", status: "Estado", amount: "Monto", date: "Fecha", channel: "Canal", place: "Lugar",
    code: "Código de respuesta", id: "Identificador", decision: "Decisión", resolution: "Resultado", by: "Por",
    resolved: "Sin cargo confirmado", escalated: "Revisión humana", opened: "Caso abierto", list: "Evidencia del caso",
    reason: "Motivo", agent: "agente",
  },
  pt: {
    transaction: "Transação", status: "Status", amount: "Valor", date: "Data", channel: "Canal", place: "Local",
    code: "Código de resposta", id: "Identificador", decision: "Decisão", resolution: "Resultado", by: "Por",
    resolved: "Sem cobrança confirmada", escalated: "Revisão humana", opened: "Caso aberto", list: "Evidência do caso",
    reason: "Motivo", agent: "agente",
  },
} as const;

export function evidenceLabel(language: Language): string {
  return TEXT[language].list;
}

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

/** The facts a case rests on, in the order a person reads them: what was charged, then what was decided. */
export function evidenceFromCase(caseData: DisputeCase, language: Language): EvidenceData[] {
  const t = TEXT[language];
  const items: EvidenceData[] = [];
  const evidence = (caseData.evidence ?? {}) as Record<string, unknown>;
  const tx = evidence.transaction as Record<string, unknown> | undefined;
  if (tx) {
    const meaning = (tx.response_meaning as Record<string, string> | undefined)?.[language];
    const place = [text(tx.transaction_city), text(tx.transaction_country)].filter(Boolean).join(", ");
    const amount = formatAmount(tx.amount_usd_effective as number | string | undefined ?? tx.amount as number | string | undefined, language);
    items.push({
      id: "transaction",
      kind: "transaction",
      title: text(tx.merchant_name) || t.transaction,
      subtitle: `${amount} · ${transactionStatusLabel(text(tx.transaction_status), language)}`,
      details: [
        [t.id, text(tx.transaction_id)],
        [t.amount, amount],
        [t.status, transactionStatusLabel(text(tx.transaction_status), language)],
        [t.date, formatDate(text(tx.transaction_date), language)],
        [t.channel, text(tx.channel)],
        [t.place, place],
        ...(tx.response_code ? [[t.code, `${text(tx.response_code)}${meaning ? ` · ${meaning}` : ""}`] as [string, string]] : []),
      ].filter(([, value]) => value && value !== "-") as Array<[string, string]>,
    });
  }
  const events = caseData.events ?? [];
  const closing = events.find((event) => event.event === "auto_resolved");
  if (closing || caseData.status === "auto_resolved") {
    items.push({
      id: "decision",
      kind: "decision",
      title: t.resolved,
      subtitle: `${t.by} ${t.agent}`,
      details: [
        [t.decision, caseStatusLabel("auto_resolved", language)],
        [t.resolution, text(closing?.payload?.resolution)],
        [t.date, formatDate(closing?.ts ?? caseData.resolved_at, language)],
      ].filter(([, value]) => value && value !== "-") as Array<[string, string]>,
    });
  } else if (caseData.status === "escalated" || caseData.handoff) {
    const handoff = (evidence.handoff ?? caseData.handoff) as Record<string, unknown> | undefined;
    items.push({
      id: "handoff",
      kind: "handoff",
      title: t.escalated,
      subtitle: handoff?.reason ? reasonLabel(String(handoff.reason), language) : undefined,
      details: [
        [t.reason, text(handoff?.reason)],
        [t.decision, caseStatusLabel(caseData.status, language)],
      ].filter(([, value]) => value) as Array<[string, string]>,
    });
  }
  return items;
}
