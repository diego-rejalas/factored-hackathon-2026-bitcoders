"use client";

import { useEffect, useRef, useState } from "react";
import { tr } from "@/lib/i18n";
import type { CaseListItem, DisputeCase, Language } from "@/lib/types";
import { formatDate } from "@/lib/types";

export default function CasesPanel({
  agentUrl,
  token,
  language,
  onClose,
}: {
  agentUrl: string;
  token: string;
  language: Language;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [selected, setSelected] = useState<DisputeCase | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      if (dialog?.open) dialog.close();
    };
  }, []);

  async function loadCases() {
    setLoading(true);
    setError(false);
    try {
      const response = await fetch(`${agentUrl}/me/disputes`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (!response.ok) throw new Error("cases unavailable");
      setCases((await response.json()) as CaseListItem[]);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadCases();
    // The dialog is mounted only while open; this is one load per opening.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentUrl, token]);

  async function openCase(caseId: string) {
    setDetailLoading(true);
    setSelected(null);
    try {
      const response = await fetch(`${agentUrl}/disputes/${encodeURIComponent(caseId)}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (!response.ok) throw new Error("case unavailable");
      setSelected((await response.json()) as DisputeCase);
    } catch {
      setError(true);
    } finally {
      setDetailLoading(false);
    }
  }

  function closeDialog() {
    if (dialogRef.current?.open) dialogRef.current.close();
    else onClose();
  }

  return (
    <dialog
      ref={dialogRef}
      className="drawer"
      aria-labelledby="my-cases-title"
      onClose={onClose}
    >
      <header>
        <h2 id="my-cases-title">{tr(language, "casesTitle")}</h2>
        <button className="btn-ghost" type="button" onClick={closeDialog}>
          {tr(language, "close")}
        </button>
      </header>
      <div className="drawer-body">
        {selected ? (
          <>
            <button className="backlink" type="button" onClick={() => setSelected(null)}>
              ← {tr(language, "back")}
            </button>
            <section className="case-detail-summary">
              <div className="case-row-static">
                <div className="top">
                  <code className="mono">{selected.case_id}</code>
                  <span className={`badge badge-${selected.status}`}>{selected.status}</span>
                </div>
                <div className="sub">
                  {tr(language, "transaction")}: <span className="mono">{selected.transaction_id || tr(language, "unlinkedTransaction")}</span>
                  {selected.created_at ? ` · ${formatDate(selected.created_at, language)}` : ""}
                </div>
              </div>
              <h3>{tr(language, "caseTimeline")}</h3>
              {selected.events?.length ? (
                <ol className="timeline">
                  {selected.events.map((event, index) => (
                    <li className={index === selected.events!.length - 1 ? "tl-accent" : ""} key={`${event.event}-${index}`}>
                      {eventLabel(event.event, language)}
                      <time className="when" dateTime={event.ts || undefined}>
                        {formatDate(event.ts, language)}
                      </time>
                    </li>
                  ))}
                </ol>
              ) : <p className="empty">{tr(language, "noEvents")}</p>}
            </section>
          </>
        ) : detailLoading ? (
          <div className="skeleton" aria-label={tr(language, "loading")} style={{ height: "6rem" }} />
        ) : loading ? (
          <div className="skeleton" aria-label={tr(language, "loading")} style={{ height: "7rem" }} />
        ) : error ? (
          <div className="alert alert-error" role="alert">
            {tr(language, "connectError")}
            <button className="btn-ghost retry-button" type="button" onClick={() => void loadCases()}>
              {tr(language, "retry")}
            </button>
          </div>
        ) : cases.length === 0 ? (
          <p className="empty">{tr(language, "noCases")}</p>
        ) : (
          cases.map((item) => (
            <button className="case-row" type="button" key={item.case_id} onClick={() => void openCase(item.case_id)}>
              <span className="top">
                <code className="mono">{item.case_id}</code>
                <span className={`badge badge-${item.status}`}>{item.status}</span>
              </span>
              <span className="sub">
                {tr(language, "transaction")}: {item.transaction_id || tr(language, "unlinkedTransaction")} · {formatDate(item.created_at, language)}
              </span>
            </button>
          ))
        )}
      </div>
    </dialog>
  );
}

function eventLabel(event: string, language: Language): string {
  const keys: Record<string, string> = {
    created: "eventCreated",
    auto_resolved: "eventAutoResolved",
    escalated: "eventEscalated",
    admin_claim: "eventAdminClaim",
    admin_close: "eventAdminClose",
  };
  return tr(language, keys[event] ?? "unknownEvent");
}
