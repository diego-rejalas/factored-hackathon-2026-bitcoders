"use client";

import { FormEvent, useRef, useState } from "react";

const FALLBACK_AGENT_URL = "http://localhost:8001";

type Outcome = "resolved" | "clarify" | "escalated";

type Handoff = {
  case_id?: string;
  reason?: string;
  request?: { es?: string; pt?: string };
};

type Message = {
  role: "user" | "bot";
  text: string;
  outcome?: Outcome;
  handoff?: Handoff | null;
};

const OUTCOME_LABEL: Record<Outcome, string> = {
  resolved: "resuelto",
  clarify: "aclaración",
  escalated: "escalado a humano",
};

export default function Chat({ agentUrl }: { agentUrl: string }) {
  const AGENT_URL = agentUrl.replace(/\/$/, "");
  const [token, setToken] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  if (!token) {
    return (
      <Login
        agentUrl={AGENT_URL}
        onLogin={(t) => {
          setToken(t);
          setSessionExpired(false);
          setError(null);
          setMessages([
            {
              role: "bot",
              text:
                "Hola. Te ayudo con cobros que no reconozcas o transacciones rechazadas/revertidas. Cuéntame qué pasó.",
              outcome: "resolved",
            },
          ]);
        }}
        sessionExpired={sessionExpired}
      />
    );
  }

  async function send(event?: FormEvent) {
    event?.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", text }]);
    setBusy(true);
    try {
      const response = await fetch(`${AGENT_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_token: token,
          message: text,
          conversation_id: conversationId,
        }),
      });
      if (response.status === 401) {
        setSessionExpired(true);
        setToken(null);
        return;
      }
      if (!response.ok) {
        throw new Error(`agent ${response.status}`);
      }
      const body = await response.json();
      setConversationId(body.conversation_id);
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: body.reply, outcome: body.outcome, handoff: body.handoff },
      ]);
    } catch {
      setError("No pude contactar al agente. Intenta de nuevo.");
    } finally {
      setBusy(false);
      requestAnimationFrame(() => listRef.current?.scrollTo(0, listRef.current.scrollHeight));
    }
  }

  return (
    <main className="chat">
      <header className="chat-header">
        <h1>Asistencia bancaria</h1>
        <button
          onClick={() => {
            setToken(null);
            setConversationId(null);
            setMessages([]);
          }}
        >
          Cerrar sesión
        </button>
      </header>
      <div className="messages" ref={listRef}>
        {messages.map((msg, index) => (
          <div key={index}>
            <div className={`msg ${msg.role}`}>{msg.text}</div>
            {msg.role === "bot" && msg.outcome && msg.outcome !== "escalated" && (
              <span className={`badge ${msg.outcome}`}>{OUTCOME_LABEL[msg.outcome]}</span>
            )}
            {msg.role === "bot" && msg.handoff && (
              <div className="handoff">
                Escalado a un agente humano
                {msg.handoff.case_id ? (
                  <>
                    {" — caso "} <code>{msg.handoff.case_id}</code>
                  </>
                ) : null}
                {" · motivo: "}
                {msg.handoff.reason || "revisión humana"}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="msg bot">Escribiendo…</div>}
      </div>
      {error && (
        <div style={{ padding: "0 1rem 0.5rem" }}>
          <span className="error">{error}</span>
        </div>
      )}
      <form className="composer" onSubmit={send}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe tu mensaje…"
          aria-label="Mensaje"
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Enviar
        </button>
      </form>
    </main>
  );
}

function Login({
  agentUrl,
  onLogin,
  sessionExpired,
}: {
  agentUrl: string;
  onLogin: (token: string) => void;
  sessionExpired: boolean;
}) {
  const [customerId, setCustomerId] = useState("");
  const [documentNumber, setDocumentNumber] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!customerId.trim() || !documentNumber.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${agentUrl}/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: customerId.trim(),
          document_number: documentNumber.trim(),
        }),
      });
      if (!response.ok) {
        setError("Datos incorrectos. Revisa tu customer_id y documento.");
        return;
      }
      const body = await response.json();
      onLogin(body.session_token);
    } catch {
      setError("No pude contactar al agente.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="login-card" onSubmit={submit}>
        <h1>Asistencia bancaria</h1>
        <p>
          Acceso de prueba (sandbox): ingresa tu <strong>customer_id</strong> y{" "}
          <strong>número de documento</strong>.
        </p>
        {sessionExpired && <span className="error">Tu sesión expiró. Vuelve a ingresar.</span>}
        {error && <span className="error">{error}</span>}
        <div className="field">
          <label htmlFor="customer_id">Customer ID</label>
          <input
            id="customer_id"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            autoComplete="username"
          />
        </div>
        <div className="field">
          <label htmlFor="document_number">Número de documento</label>
          <input
            id="document_number"
            value={documentNumber}
            onChange={(e) => setDocumentNumber(e.target.value)}
            autoComplete="current-password"
          />
        </div>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </main>
  );
}
