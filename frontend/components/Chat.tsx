"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import CasesPanel from "@/components/CasesPanel";
import { EvidenceItem, EvidenceList, evidenceFromCase, evidenceLabel } from "@/components/Evidence";
import { caseStatusLabel, reasonLabel, suggestions, tr } from "@/lib/i18n";
import type { Candidate, ChatResponse, DisputeCase, Handoff, Language } from "@/lib/types";
import { formatCandidateAmount, formatDate } from "@/lib/types";

type Message = {
  role: "user" | "bot";
  text: string;
  response?: ChatResponse;
};

export default function Chat({
  agentUrl,
  token,
  firstName,
  onLogout,
}: {
  agentUrl: string;
  token: string;
  firstName?: string;
  onLogout: (expired?: boolean) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([
    { role: "bot", text: tr("es", "welcome") },
  ]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [language, setLanguage] = useState<Language>("es");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [casesOpen, setCasesOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  async function send(event?: FormEvent<HTMLFormElement>, preset?: string) {
    event?.preventDefault();
    const text = (preset ?? input).trim();
    if (!text || busy) return;
    setInput("");
    setError(null);
    setMessages((previous) => [...previous, { role: "user", text }]);
    setBusy(true);
    try {
      const response = await fetch(`${agentUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_token: token, message: text, conversation_id: conversationId }),
      });
      if (response.status === 401) {
        onLogout(true);
        return;
      }
      if (!response.ok) throw new Error(`agent ${response.status}`);
      const body = (await response.json()) as ChatResponse;
      setConversationId(body.conversation_id);
      const detected = body.language === "pt" ? "pt" : body.language === "es" ? "es" : language;
      setLanguage(detected);
      setMessages((previous) => [
        ...previous,
        { role: "bot", text: body.reply, response: body },
      ]);
    } catch {
      setError(tr(language, "connectError"));
    } finally {
      setBusy(false);
      requestAnimationFrame(() => {
        if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
      });
    }
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" && event.nativeEvent.isComposing) event.preventDefault();
  }

  function useCandidate(candidate: Candidate) {
    const amount = candidate.amount_usd_effective !== null && candidate.amount_usd_effective !== undefined
      ? `${candidate.amount_usd_effective} USD`
      : `${candidate.amount ?? ""} ${candidate.currency ?? ""}`.trim();
    const merchant = candidate.merchant_name;
    const prompt = language === "pt"
      ? `É a cobrança de ${amount ?? ""} ${merchant ? `em ${merchant}` : ""}`.trim()
      : `Fue el cobro de ${amount ?? ""} ${merchant ? `en ${merchant}` : ""}`.trim();
    setInput(prompt);
    document.getElementById("chat-message")?.focus();
  }

  return (
    <main className="chat">
      <a className="skip-link" href="#chat-message">
        {language === "pt" ? "Pular para a mensagem" : "Ir al mensaje"}
      </a>
      <header className="appbar">
        <h1><span className="mark" aria-hidden="true">B</span>{tr(language, "appTitle")}</h1>
        <div className="appbar-actions">
          {firstName && <span className="who">{firstName}</span>}
          <button className="btn-ghost" type="button" onClick={() => setCasesOpen(true)}>
            {tr(language, "myCases")}
          </button>
          <button className="btn-ghost" type="button" onClick={() => onLogout(false)}>
            {tr(language, "logout")}
          </button>
        </div>
      </header>
      <div className="messages" ref={listRef} aria-label={tr(language, "appTitle")} aria-live="polite" aria-relevant="additions text">
        {messages.map((message, index) => (
          <article className={`message-block ${message.role}`} key={`${index}-${message.role}`}>
            <div className="msg-row">
              {message.role === "bot" && <span className="avatar" aria-hidden="true">B</span>}
              <div className={`msg ${message.role}`}>{message.text}</div>
            </div>
            {index === 0 && messages.length === 1 && (
              <div className="suggestions" aria-label={tr(language, "message")}>
                {suggestions(language).map((suggestion) => (
                  <button className="chip" type="button" key={suggestion} disabled={busy} onClick={() => send(undefined, suggestion)}>
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
            {message.role === "bot" && message.response && (
              <div className="msg-meta">
                {!message.response.case && <OutcomeBadge outcome={message.response.outcome} language={language} />}
                {message.response.outcome === "clarify" && message.response.candidates && message.response.candidates.length > 0 && (
                  <CandidateCards
                    candidates={message.response.candidates}
                    language={language}
                    onSelect={useCandidate}
                  />
                )}
                {message.response.case && (
                  <VerifiedCaseCard caseData={message.response.case} language={language} />
                )}
                {message.response.handoff && (
                  <HandoffCard handoff={message.response.handoff} language={language} />
                )}
              </div>
            )}
          </article>
        ))}
        {busy && (
          <div className="msg-row" role="status">
            <span className="avatar" aria-hidden="true">B</span>
            <div className="msg bot typing"><span className="dots" aria-hidden="true"><i /><i /><i /></span>{tr(language, "typing")}</div>
          </div>
        )}
      </div>
      {error && <div className="chat-error" role="alert">{error}</div>}
      <form className="composer" onSubmit={send}>
        <label className="sr-only" htmlFor="chat-message">{tr(language, "message")}</label>
        <input
          id="chat-message"
          name="message"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={onInputKeyDown}
          placeholder={tr(language, "messagePlaceholder")}
          autoComplete="off"
          required
        />
        <button className="btn send" type="submit" disabled={busy || !input.trim()} aria-label={tr(language, "send")}>
          <span>{tr(language, "send")}</span>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </button>
      </form>
      {casesOpen && (
        <CasesPanel
          agentUrl={agentUrl}
          token={token}
          language={language}
          onClose={() => setCasesOpen(false)}
        />
      )}
    </main>
  );
}

function OutcomeBadge({ outcome, language }: { outcome: ChatResponse["outcome"]; language: Language }) {
  const label = outcome === "clarify" ? tr(language, "clarify") : outcome === "escalated" ? tr(language, "escalated") : tr(language, "resolved");
  return <span className={`badge badge-${outcome}`}>{label}</span>;
}

function CandidateCards({
  candidates,
  language,
  onSelect,
}: {
  candidates: Candidate[];
  language: Language;
  onSelect: (candidate: Candidate) => void;
}) {
  return (
    <div className="tx-cards" aria-label={tr(language, "transaction")}>
      {candidates.slice(0, 5).map((candidate) => {
        const merchant = candidate.merchant_name || tr(language, "noMerchant");
        const amount = formatCandidateAmount(candidate, language);
        const label = `${tr(language, "chooseCandidate")}: ${merchant}, ${amount}, ${formatDate(candidate.transaction_date, language)}`;
        return (
          <button
            className="tx-card"
            type="button"
            key={candidate.transaction_id}
            aria-label={label}
            onClick={() => onSelect(candidate)}
          >
            <span className="row">
              <span className="merchant">{merchant}</span>
              <span className="amount tnum">{amount}</span>
            </span>
            <span className="sub">
              <span>{formatDate(candidate.transaction_date, language)}</span>
              <span>{candidate.transaction_status || "-"}</span>
              <span className="mono">{candidate.transaction_id}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function VerifiedCaseCard({ caseData, language }: { caseData: DisputeCase; language: Language }) {
  const evidence = evidenceFromCase(caseData, language);
  const shortId = caseData.case_id.slice(0, 8);
  return (
    <section className={`case-card status-${caseData.status}`} aria-label={`${tr(language, "case")} ${caseData.case_id}`}>
      <header className="case-head">
        <div>
          <span className="case-kicker">{tr(language, "case")}</span>
          <code className="case-id mono" title={caseData.case_id}>#{shortId}</code>
        </div>
        <span className={`badge badge-${caseData.status}`}>{caseStatusLabel(caseData.status, language)}</span>
      </header>
      <p className="case-sub">
        {caseData.transaction_id ? <span className="mono">{caseData.transaction_id}</span> : tr(language, "unlinkedTransaction")}
        {caseData.resolved_at ? ` · ${formatDate(caseData.resolved_at, language)}` : ""}
      </p>
      {evidence.length > 0 && (
        <EvidenceList variant="grid" label={evidenceLabel(language)}>
          {evidence.map((item) => (
            <EvidenceItem key={item.id} data={item} language={language} />
          ))}
        </EvidenceList>
      )}
    </section>
  );
}

function HandoffCard({ handoff, language }: { handoff: Handoff; language: Language }) {
  const request = language === "pt" ? handoff.request?.pt : handoff.request?.es;
  return (
    <section className="handoff">
      <div className="handoff-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="9" cy="8" r="3" /><path d="M3.5 19c.5-3 2.7-5 5.5-5s5 2 5.5 5M16 11l2 2 3.5-4" /></svg>
      </div>
      <div className="handoff-body">
        <div className="head">{tr(language, "humanReview")}</div>
        <div className="handoff-reason">{reasonLabel(handoff.reason, language)}</div>
        {request && <p>{request}</p>}
      </div>
    </section>
  );
}
