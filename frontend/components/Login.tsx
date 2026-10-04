"use client";

import { FormEvent, useEffect, useState } from "react";
import type { DemoScenario, Language } from "@/lib/types";
import { scenarioLabel, tr } from "@/lib/i18n";

export default function Login({
  agentUrl,
  sessionExpired,
  onLogin,
}: {
  agentUrl: string;
  sessionExpired: boolean;
  onLogin: (token: string, firstName?: string) => void;
}) {
  const [customerId, setCustomerId] = useState("");
  const [documentNumber, setDocumentNumber] = useState("");
  const [firstName, setFirstName] = useState<string | undefined>();
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<DemoScenario[]>([]);
  const [scenariosError, setScenariosError] = useState(false);
  const [language, setLanguage] = useState<Language>("es");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch(`${agentUrl}/meta/demo-scenarios`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("scenarios unavailable");
        return (await response.json()) as { scenarios?: DemoScenario[] };
      })
      .then((body) => {
        if (active) setScenarios(body.scenarios ?? []);
      })
      .catch(() => {
        if (active) setScenariosError(true);
      });
    return () => {
      active = false;
    };
  }, [agentUrl]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
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
        setError(tr(language, "badCustomerCredentials"));
        return;
      }
      const body = await response.json();
      onLogin(body.session_token, firstName);
    } catch {
      setError(tr(language, "connectError"));
    } finally {
      setBusy(false);
    }
  }

  function selectScenario(scenario: DemoScenario) {
    setCustomerId(scenario.customer_id);
    setDocumentNumber(scenario.document_number);
    setFirstName(scenario.first_name);
    setSelectedScenario(scenario.scenario);
  }

  return (
    <main className="login">
      <a className="skip-link" href="#customer-login">
        {language === "pt" ? "Pular para o formulário" : "Ir al formulario"}
      </a>
      <div className="login-brand">
        <span className="mark" aria-hidden="true">B</span>
        <span>{tr(language, "appTitle")}</span>
      </div>
      <form id="customer-login" className="login-card" onSubmit={submit}>
        <div className="login-heading">
          <div className="login-heading-copy">
            <span className="eyebrow">{tr(language, "sandbox")}</span>
            <h1>{tr(language, "loginTitle")}</h1>
          </div>
          <label className="language-switch">
            <span className="sr-only">Idioma / Idioma</span>
            <select
              value={language}
              onChange={(event) => setLanguage(event.target.value as Language)}
              aria-label="Idioma / Idioma"
            >
              <option value="es">ES</option>
              <option value="pt">PT</option>
            </select>
          </label>
        </div>
        <p>{tr(language, "loginDescription")}</p>
        {sessionExpired && (
          <div className="alert alert-error" role="alert">
            {tr(language, "expired")}
          </div>
        )}
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <div className="field">
          <label htmlFor="customer_id">{tr(language, "customerId")}</label>
          <input
            id="customer_id"
            name="customer_id"
            value={customerId}
            onChange={(event) => {
              setCustomerId(event.target.value);
              setSelectedScenario(null);
              setFirstName(undefined);
            }}
            autoComplete="username"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="document_number">{tr(language, "documentNumber")}</label>
          <input
            id="document_number"
            name="document_number"
            value={documentNumber}
            onChange={(event) => {
              setDocumentNumber(event.target.value);
              setSelectedScenario(null);
              setFirstName(undefined);
            }}
            autoComplete="current-password"
            required
          />
        </div>
        <button className="btn login-submit" type="submit" disabled={busy}>
          {busy ? tr(language, "loggingIn") : tr(language, "login")}
        </button>

        <details className="scenarios">
          <summary>{tr(language, "demoScenarios")}</summary>
          {scenariosError && <p className="scenario-error">{tr(language, "scenariosUnavailable")}</p>}
          {scenarios.length > 0 && (
            <ul>
              {scenarios.map((scenario) => (
                <li key={`${scenario.scenario}-${scenario.customer_id}`}>
                  <button
                    type="button"
                    className="scenario"
                    aria-pressed={selectedScenario === scenario.scenario}
                    onClick={() => selectScenario(scenario)}
                  >
                    <span className="tag">{scenarioLabel(scenario.scenario, language)}</span>
                    <span className="hint">
                      {language === "pt" ? scenario.hint_pt : scenario.hint_es}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </details>
      </form>
      <p className="login-footnote">
        {language === "pt"
          ? "Protótipo de hackathon: os dados e as credenciais são sintéticos; nenhum dinheiro é movimentado."
          : "Prototipo de hackathon: los datos y las credenciales son sintéticos; no se mueve dinero."}
      </p>
    </main>
  );
}
