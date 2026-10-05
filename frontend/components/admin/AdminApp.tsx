"use client";

import { useState } from "react";
import AdminLogin from "@/components/admin/AdminLogin";
import AdminCaseDetail from "@/components/admin/AdminCaseDetail";
import AdminInbox from "@/components/admin/AdminInbox";
import AdminMetrics from "@/components/admin/AdminMetrics";
import { ChatCircleDots, Moon, SignOut, Sun } from "@phosphor-icons/react";
import { tr } from "@/lib/i18n";
import { useTheme } from "@/lib/useTheme";

type View = "inbox" | "case" | "metrics";

export default function AdminApp({ agentUrl }: { agentUrl: string }) {
  const [theme, toggleTheme] = useTheme();
  const [session, setSession] = useState<{ token: string; username: string } | null>(null);
  const [view, setView] = useState<View>("inbox");
  const [caseId, setCaseId] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  if (!session) {
    return (
      <AdminLogin
        agentUrl={agentUrl}
        sessionExpired={sessionExpired}
        onLogin={(token, username) => {
          setSession({ token, username });
          setSessionExpired(false);
          setView("inbox");
        }}
      />
    );
  }

  function openCase(id: string) {
    setCaseId(id);
    setView("case");
  }

  return (
    <div className="admin-shell" data-theme={theme ?? undefined}>
      <a className="skip-link" href="#admin-content">Ir al contenido principal</a>
      <header className="appbar">
        <h1><img className="mark mark-logo" src="/factored-logo.png" alt="" aria-hidden="true" />{tr("es", "adminTitle")}</h1>
        <div className="appbar-actions">
          <span className="who-chip" title={session.username}>
            <span className="who-avatar" aria-hidden="true">{session.username.slice(0, 1).toUpperCase()}</span>
            <span className="who-name">{session.username}</span>
          </span>
          <button className="appbar-btn appbar-theme" type="button" onClick={toggleTheme} aria-label="Cambiar tema" title="Cambiar tema">
            <Sun className="icon-sun" size={18} aria-hidden="true" />
            <Moon className="icon-moon" size={18} aria-hidden="true" />
          </button>
          <a className="appbar-btn" href="/" aria-label="Atención al cliente">
            <ChatCircleDots size={18} aria-hidden="true" />
            <span>Atención al cliente</span>
          </a>
          <button
            className="appbar-btn"
            type="button"
            aria-label={tr("es", "logout")}
            onClick={() => {
              setSession(null);
              setCaseId(null);
            }}
          >
            <SignOut size={18} aria-hidden="true" />
            <span>{tr("es", "logout")}</span>
          </button>
        </div>
      </header>
      <main id="admin-content" className="admin-main">
        <nav className="tabs" aria-label="Secciones de la consola">
          <button
            className="tab"
            type="button"
            aria-current={view === "inbox" || view === "case" ? "page" : undefined}
            onClick={() => setView("inbox")}
          >
            {tr("es", "inbox")}
          </button>
          <button
            className="tab"
            type="button"
            aria-current={view === "metrics" ? "page" : undefined}
            onClick={() => setView("metrics")}
          >
            {tr("es", "metrics")}
          </button>
        </nav>
        {view === "inbox" && (
          <AdminInbox
            agentUrl={agentUrl}
            token={session.token}
            onOpenCase={openCase}
            onSessionExpired={() => {
              setSession(null);
              setSessionExpired(true);
            }}
          />
        )}
        {view === "case" && caseId && (
          <AdminCaseDetail
            agentUrl={agentUrl}
            token={session.token}
            caseId={caseId}
            onBack={() => setView("inbox")}
            onSessionExpired={() => {
              setSession(null);
              setSessionExpired(true);
            }}
          />
        )}
        {view === "metrics" && (
          <AdminMetrics
            agentUrl={agentUrl}
            token={session.token}
            onSessionExpired={() => {
              setSession(null);
              setSessionExpired(true);
            }}
          />
        )}
      </main>
      <footer className="admin-footer">
        Prototipo de hackathon. Credenciales de demostración, sin IdP real ni operaciones monetarias.
      </footer>
    </div>
  );
}
