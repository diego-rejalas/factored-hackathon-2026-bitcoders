"use client";

import { FormEvent, useState } from "react";
import { tr } from "@/lib/i18n";

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
    <main className="login">
      <a className="skip-link" href="#admin-login">Ir al formulario</a>
      <div className="login-brand">
        <span className="mark" aria-hidden="true">B</span>
        <span>{tr("es", "adminTitle")}</span>
      </div>
      <form id="admin-login" className="login-card" onSubmit={submit}>
        <div className="login-heading-copy">
          <span className="eyebrow">{tr("es", "sandbox")}</span>
          <h1>{tr("es", "adminLoginTitle")}</h1>
        </div>
        <p>{tr("es", "adminLoginDescription")}</p>
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
        <button className="btn login-submit" type="submit" disabled={busy}>
          {busy ? tr("es", "loggingIn") : tr("es", "login")}
        </button>
      </form>
      <p className="login-footnote">Acceso de demostración con limitación de intentos por proceso. No es un proveedor de identidad de producción.</p>
    </main>
  );
}
