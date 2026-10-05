"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Check,
  Copy,
  FolderOpen,
  List,
  Moon,
  Plus,
  SignOut,
  SpinnerGap,
  Sun,
  UserCheck,
  X,
} from "@phosphor-icons/react";
import CasesPanel from "@/components/CasesPanel";
import { EvidenceItem, EvidenceList, evidenceFromCase, evidenceLabel } from "@/components/Evidence";
import { ct } from "@/lib/chatText";
import { useTheme } from "@/lib/useTheme";
import { caseStatusLabel, reasonLabel, suggestions, tr } from "@/lib/i18n";
import type { Candidate, ChatResponse, ConversationItem, DisputeCase, Handoff, Language, StoredMessage } from "@/lib/types";
import { formatCandidateAmount, formatDate } from "@/lib/types";

type Message = {
  id: number;
  role: "user" | "bot";
  text: string;
  response?: ChatResponse;
  animate?: boolean;
};

const DAY = 86_400_000;

// The sidebar groups conversations by how long ago they were last used, newest group first.
function groupHistory(items: ConversationItem[], language: Language) {
  const labels =
    language === "pt"
      ? { today: "Hoje", yesterday: "Ontem", week: "Últimos 7 dias", older: "Antes" }
      : { today: "Hoy", yesterday: "Ayer", week: "Últimos 7 días", older: "Antes" };
  const now = Date.now();
  const buckets: Record<keyof typeof labels, ConversationItem[]> = { today: [], yesterday: [], week: [], older: [] };
  for (const item of items) {
    const age = now - new Date(item.last_at).getTime();
    const key = age < DAY ? "today" : age < 2 * DAY ? "yesterday" : age < 7 * DAY ? "week" : "older";
    buckets[key].push(item);
  }
  return (Object.keys(labels) as (keyof typeof labels)[])
    .filter((key) => buckets[key].length > 0)
    .map((key) => ({ label: labels[key], items: buckets[key] }));
}

export default function Chat({
  agentUrl,
  token,
  firstName,
  initialLanguage = "es",
  onLogout,
}: {
  agentUrl: string;
  token: string;
  firstName?: string;
  initialLanguage?: Language;
  onLogout: (expired?: boolean) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [language, setLanguage] = useState<Language>(initialLanguage);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [casesOpen, setCasesOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [showJump, setShowJump] = useState(false);
  const [theme, toggleTheme] = useTheme();
  const [history, setHistory] = useState<ConversationItem[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stuck = useRef(true);
  const nextId = useRef(1);

  const scrollToBottom = useCallback((smooth = false) => {
    const element = scrollRef.current;
    if (!element) return;
    element.scrollTo({ top: element.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }, []);

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const loadHistory = useCallback(async () => {
    try {
      const response = await fetch(`${agentUrl}/me/conversations`, { headers: authHeaders, cache: "no-store" });
      if (response.status === 401) return onLogout(true);
      if (response.ok) setHistory((await response.json()) as ConversationItem[]);
    } catch {
      /* the list is a convenience; the chat works without it */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentUrl, authHeaders]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  async function openConversation(id: string) {
    if (busy || id === conversationId) return setMenuOpen(false);
    setError(null);
    try {
      const response = await fetch(`${agentUrl}/me/conversations/${encodeURIComponent(id)}`, { headers: authHeaders, cache: "no-store" });
      if (response.status === 401) return onLogout(true);
      if (!response.ok) throw new Error(String(response.status));
      const body = (await response.json()) as { messages: StoredMessage[] };
      setMessages(
        body.messages.map((message) => ({
          id: nextId.current++,
          role: message.role,
          text: message.text,
          response: message.response ?? undefined,
        })),
      );
      setConversationId(id);
      const last = [...body.messages].reverse().find((message) => message.response?.language);
      if (last?.response?.language) setLanguage(last.response.language === "pt" ? "pt" : "es");
      setMenuOpen(false);
      stuck.current = true;
      requestAnimationFrame(() => scrollToBottom());
    } catch {
      setError(ct(language, "loadError"));
    }
  }

  function onScroll() {
    const element = scrollRef.current;
    if (!element) return;
    const away = element.scrollHeight - element.scrollTop - element.clientHeight;
    stuck.current = away < 80;
    setShowJump(away > 240);
  }

  useEffect(() => {
    if (stuck.current) scrollToBottom(true);
  }, [messages.length, busy, scrollToBottom]);

  // The composer grows with the text, up to about six lines.
  useEffect(() => {
    const element = inputRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 168)}px`;
  }, [input]);

  async function send(event?: FormEvent<HTMLFormElement>, preset?: string) {
    event?.preventDefault();
    const text = (preset ?? input).trim();
    if (!text || busy) return;
    setInput("");
    setError(null);
    stuck.current = true;
    setMessages((previous) => [...previous, { id: nextId.current++, role: "user", text }]);
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
        { id: nextId.current++, role: "bot", text: body.reply, response: body, animate: true },
      ]);
      void loadHistory();
    } catch {
      setError(tr(language, "connectError"));
    } finally {
      setBusy(false);
    }
  }

  function newConversation() {
    setMessages([]);
    setConversationId(null);
    setError(null);
    setInput("");
    setMenuOpen(false);
    inputRef.current?.focus();
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  }

  function chooseCandidate(candidate: Candidate) {
    const amount =
      candidate.amount_usd_effective !== null && candidate.amount_usd_effective !== undefined
        ? `${candidate.amount_usd_effective} USD`
        : `${candidate.amount ?? ""} ${candidate.currency ?? ""}`.trim();
    const merchant = candidate.merchant_name;
    const prompt =
      language === "pt"
        ? `É a cobrança de ${amount} ${merchant ? `em ${merchant}` : ""}`.trim()
        : `Fue el cobro de ${amount} ${merchant ? `en ${merchant}` : ""}`.trim();
    setInput(prompt);
    inputRef.current?.focus();
  }

  const initial = (firstName || "?").slice(0, 1).toUpperCase();

  return (
    <div className="gpt" data-theme={theme ?? undefined}>
      <a className="skip-link" href="#chat-message">
        {ct(language, "skip")}
      </a>

      <aside className={`gpt-side${menuOpen ? " open" : ""}`} aria-label={ct(language, "brand")}>
        <div className="gpt-side-head">
          <img className="gpt-mark" src="/factored-logo.png" alt="" aria-hidden="true" />
          <span className="gpt-brand">{ct(language, "brand")}</span>
          <button className="gpt-icon gpt-side-close" type="button" onClick={() => setMenuOpen(false)} aria-label={ct(language, "closeMenu")}>
            <X size={20} />
          </button>
        </div>
        <nav className="gpt-nav">
          <button type="button" onClick={newConversation}>
            <Plus size={18} aria-hidden="true" />
            {ct(language, "newChat")}
          </button>
          <button
            type="button"
            onClick={() => {
              setCasesOpen(true);
              setMenuOpen(false);
            }}
          >
            <FolderOpen size={18} aria-hidden="true" />
            {ct(language, "cases")}
          </button>
        </nav>
        <div className="gpt-history">
          <h2>{ct(language, "recent")}</h2>
          {history.length === 0 ? (
            <p>{ct(language, "noRecent")}</p>
          ) : (
            <>
              {groupHistory(history, language).map((group) => (
                <section key={group.label} aria-label={group.label}>
                  <h3>{group.label}</h3>
                  <ul>
                    {group.items.map((item) => (
                      <li key={item.conversation_id}>
                        <button
                          type="button"
                          className={item.conversation_id === conversationId ? "active" : undefined}
                          aria-current={item.conversation_id === conversationId ? "true" : undefined}
                          title={formatDate(item.last_at, language)}
                          onClick={() => openConversation(item.conversation_id)}
                        >
                          {item.title || "…"}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </>
          )}
        </div>
        <button className="gpt-theme" type="button" onClick={toggleTheme}>
          <Sun className="icon-sun" size={18} aria-hidden="true" />
          <Moon className="icon-moon" size={18} aria-hidden="true" />
          {ct(language, "theme")}
        </button>
        <div className="gpt-user">
          <span className="gpt-avatar" aria-hidden="true">{initial}</span>
          <span className="gpt-user-name">{firstName}</span>
          <button className="gpt-icon" type="button" onClick={() => onLogout(false)} aria-label={ct(language, "logout")} title={ct(language, "logout")}>
            <SignOut size={18} />
          </button>
        </div>
      </aside>
      {menuOpen && <button className="gpt-scrim" type="button" aria-label={ct(language, "closeMenu")} onClick={() => setMenuOpen(false)} />}

      <main className="gpt-main">
        <header className="gpt-top">
          <button className="gpt-icon gpt-menu" type="button" onClick={() => setMenuOpen(true)} aria-label={ct(language, "menu")}>
            <List size={22} />
          </button>
          <h1>{ct(language, "tagline")}</h1>
        </header>

        <div className="gpt-scroll" ref={scrollRef} onScroll={onScroll}>
          <div className="gpt-col" aria-live="polite" aria-relevant="additions text">
            {messages.length === 0 && !busy && (
              <section className="gpt-empty">
                <img className="gpt-mark gpt-mark-lg" src="/factored-logo.png" alt="" aria-hidden="true" />
                <h2>{ct(language, "emptyTitle")}</h2>
                <p>{ct(language, "emptyBody")}</p>
                <div className="gpt-suggestions">
                  {suggestions(language).map((suggestion) => (
                    <button className="gpt-suggestion" type="button" key={suggestion} onClick={() => send(undefined, suggestion)}>
                      {suggestion}
                    </button>
                  ))}
                </div>
              </section>
            )}
            {messages.map((message) =>
              message.role === "user" ? (
                <article className="turn turn-user" key={message.id}>
                  <div className="turn-bubble">{message.text}</div>
                </article>
              ) : (
                <AssistantMessage
                  key={message.id}
                  message={message}
                  language={language}
                  onSelect={chooseCandidate}
                  onTick={() => stuck.current && scrollToBottom()}
                />
              ),
            )}
            {busy && (
              <div className="turn turn-bot" role="status" aria-label={ct(language, "typing")}>
                <span className="typing" aria-hidden="true"><i /><i /><i /></span>
              </div>
            )}
            {error && <div className="gpt-error" role="alert">{error}</div>}
          </div>
        </div>

        <div className="gpt-dock">
          {showJump && (
            <button className="gpt-jump" type="button" onClick={() => scrollToBottom(true)} aria-label={ct(language, "jump")}>
              <ArrowDown size={18} />
            </button>
          )}
          <form className="gpt-composer" onSubmit={send}>
            <label className="sr-only" htmlFor="chat-message">{tr(language, "message")}</label>
            <textarea
              id="chat-message"
              ref={inputRef}
              name="message"
              rows={1}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={onInputKeyDown}
              placeholder={ct(language, "placeholder")}
              autoComplete="off"
              enterKeyHint="send"
            />
            <button
              className="gpt-send"
              type="submit"
              disabled={busy || !input.trim()}
              aria-label={busy ? ct(language, "sending") : ct(language, "send")}
            >
              {busy ? <SpinnerGap className="spin" size={20} /> : <ArrowUp size={20} weight="bold" />}
            </button>
          </form>
          <p className="gpt-note">{ct(language, "note")}</p>
        </div>
      </main>

      {casesOpen && (
        <CasesPanel agentUrl={agentUrl} token={token} language={language} onClose={() => setCasesOpen(false)} />
      )}
    </div>
  );
}

function AssistantMessage({
  message,
  language,
  onSelect,
  onTick,
}: {
  message: Message;
  language: Language;
  onSelect: (candidate: Candidate) => void;
  onTick: () => void;
}) {
  const [done, setDone] = useState(!message.animate);
  const [copied, setCopied] = useState(false);
  const response = message.response;

  // The cards and actions appear after the text; keep the end of the conversation in view.
  useEffect(() => {
    if (done) requestAnimationFrame(onTick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard can be blocked; nothing to recover */
    }
  }

  return (
    <article className="turn turn-bot">
      <StreamingText text={message.text} animate={Boolean(message.animate)} onDone={() => setDone(true)} onTick={onTick} />
      {done && response && (
        <div className="turn-extras">
          {/* A badge says something happened to a case. A greeting, a question or an error is not a resolution. */}
          {!response.case && response.outcome === "escalated" && <OutcomeBadge outcome={response.outcome} language={language} />}
          {response.outcome === "clarify" && response.candidates && response.candidates.length > 0 && (
            <CandidateCards candidates={response.candidates} language={language} onSelect={onSelect} />
          )}
          {response.case && <VerifiedCaseCard caseData={response.case} language={language} />}
          {response.handoff && <HandoffCard handoff={response.handoff} language={language} />}
        </div>
      )}
      {done && (
        <div className="turn-actions">
          <button className="gpt-icon" type="button" onClick={copy} aria-label={copied ? ct(language, "copied") : ct(language, "copy")} title={copied ? ct(language, "copied") : ct(language, "copy")}>
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </button>
        </div>
      )}
    </article>
  );
}

/*
 * The agent answers in one piece; this reveals it word by word so the reader follows it as it arrives, and the
 * evidence cards appear once the text is complete. The two newest words are tinted. With reduced motion the
 * text appears at once.
 */
function StreamingText({
  text,
  animate,
  onDone,
  onTick,
}: {
  text: string;
  animate: boolean;
  onDone: () => void;
  onTick: () => void;
}) {
  const parts = useMemo(() => text.split(/(\s+)/), [text]);
  const total = useMemo(() => parts.filter((part) => part && !/^\s+$/.test(part)).length, [parts]);
  const [count, setCount] = useState(animate ? 0 : total);
  const doneRef = useRef(onDone);
  const tickRef = useRef(onTick);
  doneRef.current = onDone;
  tickRef.current = onTick;

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!animate || reduce) {
      setCount(total);
      doneRef.current();
      return;
    }
    let shown = 0;
    const step = Math.max(1, Math.ceil(total / 55));
    const timer = setInterval(() => {
      shown = Math.min(total, shown + step);
      setCount(shown);
      tickRef.current();
      if (shown >= total) {
        clearInterval(timer);
        doneRef.current();
      }
    }, 32);
    return () => clearInterval(timer);
  }, [animate, total]);

  const out: React.ReactNode[] = [];
  let word = 0;
  parts.forEach((part, index) => {
    if (!part) return;
    if (/^\s+$/.test(part)) {
      if (word > 0 && word < count) out.push(part);
      return;
    }
    if (word >= count) return;
    const fresh = animate && count < total && word >= count - 2;
    out.push(<span className={fresh ? "w fresh" : "w"} key={index}>{part}</span>);
    word += 1;
  });

  return (
    <p className="turn-text">
      {out}
      {animate && count < total && <span className="caret" aria-hidden="true" />}
    </p>
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
          <button className="tx-card" type="button" key={candidate.transaction_id} aria-label={label} onClick={() => onSelect(candidate)}>
            <span className="row">
              <span className="merchant">{merchant}</span>
              <span className="amount tnum">{amount}</span>
            </span>
            <span className="sub">
              <span>{formatDate(candidate.transaction_date, language)}</span>
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
        <UserCheck size={20} />
      </div>
      <div className="handoff-body">
        <div className="head">{tr(language, "humanReview")}</div>
        <div className="handoff-reason">{reasonLabel(handoff.reason, language)}</div>
        {request && <p>{request}</p>}
      </div>
    </section>
  );
}
