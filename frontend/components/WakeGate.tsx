"use client";

import { ReactNode, useEffect, useState } from "react";
import { CheckCircle, CircleNotch, Clock } from "@phosphor-icons/react";
import { tr } from "@/lib/i18n";
import type { Language } from "@/lib/types";

type Phase = "checking" | "db" | "services" | "ready";

const POLL_MS = 3000;
const SERVICES_TIMEOUT_MS = 90_000;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function waker(wakerUrl: string, path: string, method: "GET" | "POST" = "GET"): Promise<string> {
  const response = await fetch(`${wakerUrl}${path}`, { method, cache: "no-store" });
  if (!response.ok) throw new Error(`waker ${response.status}`);
  return (await response.json()).state as string;
}

async function agentAnswers(agentUrl: string): Promise<boolean> {
  try {
    return (await fetch(`${agentUrl}/health`, { cache: "no-store" })).ok;
  } catch {
    return false;
  }
}

/**
 * The demo sleeps when nobody uses it (the database is stopped). While it is asleep this screen asks the waker to start it
 * and shows how far it is; once the database and the agent answer, the app appears. When the demo is awake the screen
 * never shows. If the waker cannot be reached the app is shown anyway: a broken waker must not lock anyone out.
 * Without a wakerUrl (no waker in this environment) the children render at once.
 */
export default function WakeGate({ wakerUrl, agentUrl, children }: { wakerUrl: string; agentUrl: string; children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>(wakerUrl ? "checking" : "ready");
  const [seconds, setSeconds] = useState(0);
  const [language, setLanguage] = useState<Language>("es");

  useEffect(() => {
    setLanguage(navigator.language.toLowerCase().startsWith("pt") ? "pt" : "es");
  }, []);

  useEffect(() => {
    if (!wakerUrl) return;
    let active = true;

    (async () => {
      try {
        let state = await waker(wakerUrl, "/status");
        if (state === "asleep") {
          if (!active) return;
          setPhase("db");
          state = await waker(wakerUrl, "/wake", "POST");
        } else if (state === "waking") {
          setPhase("db");
        }
        while (active && state !== "awake") {
          await sleep(POLL_MS);
          state = await waker(wakerUrl, "/status");
        }
        if (!active) return;
        // The database is up. Cloud Run starts the agent on the first request, which takes a few seconds more.
        if (!(await agentAnswers(agentUrl))) {
          setPhase("services");
          const deadline = Date.now() + SERVICES_TIMEOUT_MS;
          while (active && Date.now() < deadline && !(await agentAnswers(agentUrl))) await sleep(2000);
        }
      } catch {
        // The waker is unreachable: show the app instead of keeping someone out.
      }
      if (active) setPhase("ready");
    })();

    return () => {
      active = false;
    };
  }, [wakerUrl, agentUrl]);

  useEffect(() => {
    if (phase !== "db" && phase !== "services") return;
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  if (phase === "ready") return <>{children}</>;
  if (phase === "checking") return <div className="login" aria-busy="true" />;

  const steps = [
    { label: tr(language, "wakeStepDb"), status: phase === "db" ? "working" : "done" },
    { label: tr(language, "wakeStepServices"), status: phase === "db" ? "waiting" : "working" },
  ] as const;
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

  return (
    <main className="login">
      <div className="login-card wake-card" role="status" aria-live="polite">
        <h1>{tr(language, "wakeTitle")}</h1>
        <p>{tr(language, "wakeIntro")}</p>
        <ul className="wake-steps">
          {steps.map((step) => (
            <li key={step.label} className={`wake-step wake-${step.status}`}>
              {step.status === "done" ? (
                <CheckCircle size={20} weight="fill" aria-hidden />
              ) : step.status === "working" ? (
                <CircleNotch size={20} className="wake-spin" aria-hidden />
              ) : (
                <Clock size={20} aria-hidden />
              )}
              <span>{step.label}</span>
              <span className="wake-state">
                {tr(language, step.status === "done" ? "wakeDone" : step.status === "working" ? "wakeWorking" : "wakeWaiting")}
              </span>
            </li>
          ))}
        </ul>
        <div className="wake-bar" aria-hidden>
          <span className="wake-bar-fill" />
        </div>
        <p>
          {tr(language, "wakeEta")} · {tr(language, "wakeElapsed")}: {clock}
        </p>
      </div>
    </main>
  );
}
