"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import CasesPanel from "@/components/CasesPanel";
import { reasonLabel, tr } from "@/lib/i18n";
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

  async function send(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const text = input.trim();
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
            <div className={`msg ${message.role}`}>{message.text}</div>
            {message.role === "bot" && message.response && (
              <div className="msg-meta">
                <OutcomeBadge outcome={message.response.outcome} language={language} />
                {message.response.candidates && message.response.candidates.length > 0 && (
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
        {busy && <div className="msg bot" role="status">{tr(language, "typing")}</div>}
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
        <button className="btn" type="submit" disabled={busy || !input.trim()}>
          {tr(language, "send")}
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
  return (
    <section className="case-card" aria-label={`${tr(language, "case")} ${caseData.case_id}`}>
      <div className="head">
        <span>{tr(language, "case")}</span>
        <code className="mono">{caseData.case_id}</code>
        <span className={`badge badge-${caseData.status}`}>{caseData.status}</span>
      </div>
      <div className="sub">
        {tr(language, "transaction")}: <span className="mono">{caseData.transaction_id || tr(language, "unlinkedTransaction")}</span>
        {caseData.resolved_at ? ` · ${formatDate(caseData.resolved_at, language)}` : ""}
      </div>
    </section>
  );
}

function HandoffCard({ handoff, language }: { handoff: Handoff; language: Language }) {
  const request = language === "pt" ? handoff.request?.pt : handoff.request?.es;
  return (
    <section className="handoff">
      <div className="head">{tr(language, "humanReview")}</div>
      <div>{tr(language, "reason")}: {reasonLabel(handoff.reason, language)}</div>
      {handoff.case_id && <div>{tr(language, "case")}: <code className="mono">{handoff.case_id}</code></div>}
      {request && <p>{request}</p>}
    </section>
  );
}
