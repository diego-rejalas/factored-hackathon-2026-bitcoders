"use client";

import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle, CircleNotch, Clock } from "@phosphor-icons/react";
import { tr } from "@/lib/i18n";
import type { Language } from "@/lib/types";

// "checking": first look at the waker. "db" and "services": waking. "ready": the app is shown.
type Phase = "checking" | "db" | "services" | "ready";

const POLL_MS = 3000;
// After a wake the backend builds the demo scenarios on a database whose caches are empty, which took close to two minutes.
const SERVICES_TIMEOUT_MS = 300_000;
// How long the first look at the waker may take before the waiting screen shows (a cold waker needs a few seconds).
const SLOW_CHECK_MS = 1500;
// The waker stops the database after a quiet spell. A tab that is open and used says so every few minutes, so
// reading a case for a while never puts the demo to sleep under the reader.
const HEARTBEAT_MS = 4 * 60_000;
const ACTIVE_WINDOW_MS = 20 * 60_000;
// Coming back to the tab after this long is the moment to ask the waker again.
const RECHECK_AFTER_MS = 60_000;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function waker(wakerUrl: string, path: string, method: "GET" | "POST" = "GET"): Promise<string> {
  const response = await fetch(`${wakerUrl}${path}`, { method, cache: "no-store" });
  if (!response.ok) throw new Error(`waker ${response.status}`);
  return (await response.json()).state as string;
}

// The demo scenarios are the heaviest first request: they start the backend from zero and build its cache, which takes
// about half a minute. The agent answers them through the backend, so a 200 here means the whole chain is up.
async function servicesAnswer(agentUrl: string): Promise<boolean> {
  try {
    return (await fetch(`${agentUrl}/meta/demo-scenarios`, { cache: "no-store" })).ok;
  } catch {
    return false;
  }
}

/**
 * The demo sleeps when nobody uses it (the database is stopped). While it is asleep this screen asks the waker to start it
 * and shows how far it is; once the database, the agent and the backend answer, the app appears. When the demo is awake the
 * screen never shows. If the waker cannot be reached the app is shown anyway: a broken waker must not lock anyone out.
 * Without a wakerUrl (no waker in this environment) the children render at once.
 *
 * After the app is shown the gate keeps two promises: a heartbeat while the tab is visible and in use (so the demo does not
 * sleep under an open session), and a check when the tab comes back to the front after a while: if the demo went to sleep
 * meanwhile, the waiting screen covers the app (which stays mounted, so nobody loses a session) until it is awake again.
 */
export default function WakeGate({ wakerUrl, agentUrl, children }: { wakerUrl: string; agentUrl: string; children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>(wakerUrl ? "checking" : "ready");
  const [shownOnce, setShownOnce] = useState(!wakerUrl);
  const [seconds, setSeconds] = useState(0);
  const [language, setLanguage] = useState<Language>("es");
  const [slowCheck, setSlowCheck] = useState(false);
  const running = useRef(false);
  const lastCheck = useRef(Date.now());
  const lastActivity = useRef(Date.now());

  useEffect(() => {
    setLanguage(navigator.language.toLowerCase().startsWith("pt") ? "pt" : "es");
  }, []);

  // One pass of: is it awake? if not, wake it; then wait for the database and for the services behind it.
  const wakeUp = useCallback(async () => {
    if (!wakerUrl || running.current) return;
    running.current = true;
    try {
      let state = await waker(wakerUrl, "/status");
      if (state === "asleep") {
        setSeconds(0);
        setPhase("db");
        state = await waker(wakerUrl, "/wake", "POST");
      } else if (state === "waking") {
        setSeconds(0);
        setPhase("db");
      }
      while (state !== "awake") {
        await sleep(POLL_MS);
        state = await waker(wakerUrl, "/status");
      }
      // Show the second step before the first probe, which can last half a minute: the screen must never be blank.
      setSeconds(0);
      setPhase("services");
      const deadline = Date.now() + SERVICES_TIMEOUT_MS;
      while (Date.now() < deadline && !(await servicesAnswer(agentUrl))) await sleep(2000);
    } catch {
      // The waker is unreachable: show the app instead of keeping someone out.
    } finally {
      running.current = false;
      lastCheck.current = Date.now();
      setShownOnce(true);
      setPhase("ready");
    }
  }, [wakerUrl, agentUrl]);

  useEffect(() => {
    void wakeUp();
  }, [wakeUp]);

  // A first look at the waker that takes more than a moment (it may be starting from zero) must not show a blank page.
  useEffect(() => {
    if (phase !== "checking") return;
    const timer = setTimeout(() => setSlowCheck(true), SLOW_CHECK_MS);
    return () => clearTimeout(timer);
  }, [phase]);

  // The elapsed clock of the waiting screen.
  useEffect(() => {
    if (phase !== "db" && phase !== "services" && !(phase === "checking" && slowCheck)) return;
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [phase, slowCheck]);

  // What counts as use, for the heartbeat.
  useEffect(() => {
    if (!wakerUrl) return;
    const mark = () => {
      lastActivity.current = Date.now();
    };
    const events = ["pointerdown", "keydown", "touchstart", "scroll"] as const;
    events.forEach((name) => window.addEventListener(name, mark, { passive: true }));
    return () => events.forEach((name) => window.removeEventListener(name, mark));
  }, [wakerUrl]);

  // The heartbeat: one cheap request to the agent, which the waker counts as use.
  useEffect(() => {
    if (!wakerUrl || phase !== "ready") return;
    const timer = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastActivity.current > ACTIVE_WINDOW_MS) return;
      fetch(`${agentUrl}/health`, { cache: "no-store" }).catch(() => undefined);
    }, HEARTBEAT_MS);
    return () => clearInterval(timer);
  }, [wakerUrl, agentUrl, phase]);

  // Back to the tab after a while: if the demo went to sleep meanwhile, cover the app with the waiting screen.
  useEffect(() => {
    if (!wakerUrl || phase !== "ready") return;
    const recheck = () => {
      if (document.visibilityState !== "visible" || Date.now() - lastCheck.current < RECHECK_AFTER_MS) return;
      lastCheck.current = Date.now();
      void (async () => {
        try {
          if ((await waker(wakerUrl, "/status")) !== "awake") void wakeUp();
        } catch {
          // Unreachable waker: leave the app as it is.
        }
      })();
    };
    document.addEventListener("visibilitychange", recheck);
    window.addEventListener("focus", recheck);
    return () => {
      document.removeEventListener("visibilitychange", recheck);
      window.removeEventListener("focus", recheck);
    };
  }, [wakerUrl, phase, wakeUp]);

  const waiting = phase === "db" || phase === "services";

  // The app underneath must not scroll while the waiting screen covers it.
  const covering = waiting && shownOnce;
  useEffect(() => {
    if (!covering) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [covering]);
  if (phase === "checking") {
    return slowCheck ? <WaitingScreen phase="db" seconds={seconds} language={language} /> : <div className="login" aria-busy="true" />;
  }
  // The first time the app must not render until it can load; later it stays mounted underneath the waiting screen.
  if (!shownOnce) return <WaitingScreen phase={phase} seconds={seconds} language={language} />;
  return (
    <>
      {children}
      {waiting && (
        <div className="wake-overlay">
          <WaitingScreen phase={phase} seconds={seconds} language={language} />
        </div>
      )}
    </>
  );
}

function WaitingScreen({ phase, seconds, language }: { phase: Phase; seconds: number; language: Language }) {
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
