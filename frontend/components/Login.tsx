"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { CaretDown, CheckCircle, Gauge, Moon, Question, ShieldWarning, Sun } from "@phosphor-icons/react";
import { ct } from "@/lib/chatText";
import { scenarioLabel, tr } from "@/lib/i18n";
import type { DemoScenario, Language } from "@/lib/types";
import { useTheme } from "@/lib/useTheme";

const SCENARIO_ICON = {
  auto_resolved: CheckCircle,
  ambiguous: Question,
  fraud: ShieldWarning,
  threshold: Gauge,
} as const;

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
  const [theme, toggleTheme] = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

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
    setMenuOpen(false);
  }

  return (
    <main className="auth" data-theme={theme ?? undefined}>
      <a className="skip-link" href="#customer-login">
        {language === "pt" ? "Pular para o formulário" : "Ir al formulario"}
      </a>

      <section className="auth-pane">
        <button className="gpt-icon auth-theme" type="button" onClick={toggleTheme} aria-label={ct(language, "theme")} title={ct(language, "theme")}>
          <Sun className="icon-sun" size={20} />
          <Moon className="icon-moon" size={20} />
        </button>

        <form id="customer-login" className="auth-card" onSubmit={submit}>
          <div className="auth-brand auth-brand-small">
            <span className="gpt-mark" aria-hidden="true">L</span>
            <span>{ct(language, "brand")}</span>
          </div>
          <div className="auth-heading">
            <h1>{tr(language, "loginTitle")}</h1>
            <div className="lang-toggle" role="radiogroup" aria-label="Idioma / Idioma">
              {(["es", "pt"] as const).map((code) => (
                <button
                  key={code}
                  type="button"
                  role="radio"
                  aria-checked={language === code}
                  className="lang-option"
                  onClick={() => setLanguage(code)}
                >
                  {code.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <p className="auth-lead">{tr(language, "loginDescription")}</p>
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
          <button className="auth-submit" type="submit" disabled={busy}>
            {busy ? tr(language, "loggingIn") : tr(language, "login")}
          </button>

          <div className="auth-demo">
            <h2>{ct(language, "demo")}</h2>
            <p>{ct(language, "demoHint")}</p>
            {scenariosError && <p className="scenario-error">{tr(language, "scenariosUnavailable")}</p>}
            {scenarios.length > 0 && (
              <div className="scenario-menu" ref={menuRef}>
                <button
                  type="button"
                  className="scenario-trigger"
                  aria-haspopup="listbox"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((open) => !open)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setMenuOpen(false);
                  }}
                >
                  {(() => {
                    const chosen = scenarios.find((item) => item.scenario === selectedScenario);
                    const Icon = chosen ? SCENARIO_ICON[chosen.scenario] ?? Question : Question;
                    return (
                      <>
                        <span className="auth-scenario-icon" aria-hidden="true"><Icon size={20} /></span>
                        <span className="auth-scenario-text">
                          <span className="tag">
                            {chosen ? scenarioLabel(chosen.scenario, language) : language === "pt" ? "Escolha um cenário" : "Elige un escenario"}
                          </span>
                          {chosen && <span className="hint">{language === "pt" ? chosen.hint_pt : chosen.hint_es}</span>}
                        </span>
                        <CaretDown className="scenario-caret" size={16} aria-hidden="true" />
                      </>
                    );
                  })()}
                </button>
                {menuOpen && (
                  <ul className="scenario-list" role="listbox" aria-label={ct(language, "demo")}>
                    {scenarios.map((scenario) => {
                      const Icon = SCENARIO_ICON[scenario.scenario] ?? Question;
                      return (
                        <li key={`${scenario.scenario}-${scenario.customer_id}`} role="presentation">
                          <button
                            type="button"
                            role="option"
                            className="auth-scenario"
                            aria-selected={selectedScenario === scenario.scenario}
                            onClick={() => selectScenario(scenario)}
                          >
                            <span className="auth-scenario-icon" aria-hidden="true"><Icon size={20} /></span>
                            <span className="auth-scenario-text">
                              <span className="tag">{scenarioLabel(scenario.scenario, language)}</span>
                              <span className="hint">{language === "pt" ? scenario.hint_pt : scenario.hint_es}</span>
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            )}
          </div>
        </form>
        <p className="auth-footnote">{ct(language, "note")}</p>
      </section>
    </main>
  );
}
