"use client";

import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle, CircleNotch, Clock, WarningCircle } from "@phosphor-icons/react";
import { tr } from "@/lib/i18n";
import type { Language } from "@/lib/types";

// "checking": first look at the waker. "db", "services" and "scenarios": waking, one step each. "failed": it did not come up in
// time. "ready": the app is shown.
type Phase = "checking" | "db" | "services" | "scenarios" | "failed" | "ready";

const POLL_MS = 3000;
const PROBE_MS = 2000;
// Everything is asleep when nobody uses it: the database, the backend and the agent. Waking all of it, and checking it from the
// inside, can take a few minutes. The screen says up to five; it waits a little more before it gives up.
const TOTAL_TIMEOUT_MS = 6 * 60_000;
// How long the first look at the waker may take before the waiting screen shows (a cold waker needs a few seconds).
const SLOW_CHECK_MS = 1500;
// The waker stops the database after a quiet spell. A tab that is open and used says so every few minutes, so reading a case
// for a while never puts the demo to sleep under the reader.
const HEARTBEAT_MS = 4 * 60_000;
const ACTIVE_WINDOW_MS = 20 * 60_000;
// Coming back to the tab after this long is the moment to ask the waker again.
const RECHECK_AFTER_MS = 60_000;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function waker(wakerUrl: string, path: string, method: "GET" | "POST" = "GET"): Promise<string | null> {
  try {
    const response = await fetch(`${wakerUrl}${path}`, { method, cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()).state as string;
  } catch {
    return null; // unreachable: the services themselves will say whether they are up
  }
}

async function answers(url: string): Promise<boolean> {
  try {
    return (await fetch(url, { cache: "no-store" })).ok;
  } catch {
    return false;
  }
}

class TimedOut extends Error {}

/**
 * The demo sleeps when nobody uses it: the database, the backend and the agent. This screen wakes all of it and lets the login
 * through only when everything works, checked from the inside, whatever it takes (up to a few minutes):
 *   1. the database: the waker says it is awake;
 *   2. the services: the agent's /ready runs a query through its own connections and through the backend's, twice in a row;
 *   3. the demo scenarios: the heaviest first request, which the backend builds from scratch after a cold start.
 * If it does not come up in time it says so and offers to try again; it never shows a login that cannot work. When the waker
 * cannot be reached, the services alone decide. When the demo is awake the screen never shows. Without a wakerUrl (no waker in
 * this environment) the children render at once.
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

  const wakeUp = useCallback(async () => {
    if (!wakerUrl || running.current) return;
    running.current = true;
    const deadline = Date.now() + TOTAL_TIMEOUT_MS;
    const left = () => {
      if (Date.now() > deadline) throw new TimedOut();
    };
    try {
      setSeconds(0);
      // 1. The database.
      let state = await waker(wakerUrl, "/status");
      if (state === "asleep") {
        setPhase("db");
        state = await waker(wakerUrl, "/wake", "POST");
      } else if (state === "waking") {
        setPhase("db");
      }
      while (state === "asleep" || state === "waking") {
        left();
        await sleep(POLL_MS);
        state = await waker(wakerUrl, "/status");
      }
      // 2. The services, from the inside. Twice in a row, so that one lucky answer is not taken for the whole.
      setPhase("services");
      for (let streak = 0; streak < 2; ) {
        left();
        if (await answers(`${agentUrl}/ready`)) {
          streak += 1;
          if (streak < 2) await sleep(1000);
        } else {
          streak = 0;
          await sleep(PROBE_MS);
        }
      }
      // 3. The scenarios.
      setPhase("scenarios");
      while (!(await answers(`${agentUrl}/meta/demo-scenarios`))) {
        left();
        await sleep(PROBE_MS);
      }
      lastCheck.current = Date.now();
      setShownOnce(true);
      setPhase("ready");
    } catch (error) {
      if (!(error instanceof TimedOut)) throw error;
      setPhase("failed");
    } finally {
      running.current = false;
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

  const waiting = phase === "db" || phase === "services" || phase === "scenarios";

  // The elapsed clock of the waiting screen.
  useEffect(() => {
    if (!waiting && !(phase === "checking" && slowCheck)) return;
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [waiting, phase, slowCheck]);

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
        const state = await waker(wakerUrl, "/status");
        if (state === "asleep" || state === "waking") void wakeUp();
      })();
    };
    document.addEventListener("visibilitychange", recheck);
    window.addEventListener("focus", recheck);
    return () => {
      document.removeEventListener("visibilitychange", recheck);
      window.removeEventListener("focus", recheck);
    };
  }, [wakerUrl, phase, wakeUp]);

  // The app underneath must not scroll while the waiting screen covers it.
  const covering = (waiting || phase === "failed") && shownOnce;
  useEffect(() => {
    if (!covering) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [covering]);

  const screen = <WaitingScreen phase={phase} seconds={seconds} language={language} onRetry={() => void wakeUp()} />;
  if (phase === "checking") return slowCheck ? screen : <div className="login" aria-busy="true" />;
  // The first time the app must not render until it can work; later it stays mounted underneath the waiting screen.
  if (!shownOnce) return screen;
  return (
    <>
      {children}
      {(waiting || phase === "failed") && <div className="wake-overlay">{screen}</div>}
    </>
  );
}

function WaitingScreen({ phase, seconds, language, onRetry }: { phase: Phase; seconds: number; language: Language; onRetry: () => void }) {
  if (phase === "failed") {
    return (
      <main className="login">
        <div className="login-card wake-card" role="alert">
          <h1 className="wake-failed-title">
            <WarningCircle size={22} aria-hidden /> {tr(language, "wakeFailedTitle")}
          </h1>
          <p>{tr(language, "wakeFailed")}</p>
          <button type="button" className="auth-submit" onClick={onRetry}>
            {tr(language, "wakeRetry")}
          </button>
        </div>
      </main>
    );
  }
  const index = phase === "db" || phase === "checking" ? 0 : phase === "services" ? 1 : 2;
  const labels = [tr(language, "wakeStepDb"), tr(language, "wakeStepServices"), tr(language, "wakeStepScenarios")];
  const steps = labels.map((label, i) => ({ label, status: i < index ? "done" : i === index ? "working" : "waiting" }) as const);
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
