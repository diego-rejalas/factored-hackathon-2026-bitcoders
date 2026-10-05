"use client";

import { FormEvent, useState } from "react";
import { Moon, Sun } from "@phosphor-icons/react";
import { tr } from "@/lib/i18n";
import { useTheme } from "@/lib/useTheme";

export default function AdminLogin({
  agentUrl,
  sessionExpired,
  onLogin,
}: {
  agentUrl: string;
  sessionExpired: boolean;
  onLogin: (token: string, username: string) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, toggleTheme] = useTheme();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${agentUrl}/admin/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (!response.ok) {
        setError(response.status === 429
          ? "Demasiados intentos. Espera un minuto antes de volver a probar."
          : "Usuario o contraseña incorrectos.");
        return;
      }
      const body = await response.json();
      onLogin(body.session_token, username.trim());
    } catch {
      setError(tr("es", "connectError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth" data-theme={theme ?? undefined}>
      <a className="skip-link" href="#admin-login">Ir al formulario</a>
      <section className="auth-pane">
        <button className="gpt-icon auth-theme" type="button" onClick={toggleTheme} aria-label="Cambiar tema" title="Cambiar tema">
          <Sun className="icon-sun" size={20} />
          <Moon className="icon-moon" size={20} />
        </button>

        <form id="admin-login" className="auth-card" onSubmit={submit}>
          <div className="auth-brand auth-brand-small">
            <img className="gpt-mark" src="/factored-logo.png" alt="" aria-hidden="true" />
            <span>{tr("es", "adminTitle")}</span>
          </div>
          <div className="auth-heading">
            <h1>{tr("es", "adminLoginTitle")}</h1>
          </div>
          <p className="auth-lead">{tr("es", "adminLoginDescription")}</p>
          {sessionExpired && <div className="alert alert-error" role="alert">La sesión administrativa expiró. Ingresa de nuevo.</div>}
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <div className="field">
            <label htmlFor="admin-username">{tr("es", "username")}</label>
            <input
              id="admin-username"
              name="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="admin-password">{tr("es", "password")}</label>
            <input
              id="admin-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>
          <button className="auth-submit" type="submit" disabled={busy}>
            {busy ? tr("es", "loggingIn") : tr("es", "login")}
          </button>
        </form>
        <p className="auth-footnote">Acceso de demostración con limitación de intentos por proceso. No es un proveedor de identidad de producción.</p>
      </section>
    </main>
  );
}
