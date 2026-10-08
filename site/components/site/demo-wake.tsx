"use client";

import { useEffect, useRef, useState } from "react";
import { CircleNotch, X } from "@phosphor-icons/react";

import { LINKS, WAKER_URL } from "@/lib/links";

type Phase = "idle" | "waking" | "failed";

const POLL_MS = 3000;

async function waker(path: string, method: "GET" | "POST" = "GET"): Promise<string> {
  const response = await fetch(`${WAKER_URL}${path}`, { method, cache: "no-store" });
  if (!response.ok) throw new Error(`waker ${response.status}`);
  return (await response.json()).state as string;
}

// The demo sleeps when nobody uses it. Every "Live demo" link on the page goes through here: if the demo is awake the link
// works as usual; if it is asleep this wakes it, shows how long it has been, and opens the app when it is ready. It listens on
// the document, so the links themselves stay plain links (and still work if this script does not load).
export function DemoWake() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [seconds, setSeconds] = useState(0);
  const run = useRef(0);

  useEffect(() => {
    if (!WAKER_URL || !LINKS.demo) return;
    const demo = new URL(LINKS.demo, window.location.href).href;

    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = (event.target as Element | null)?.closest("a");
      if (!link || link.href !== demo) return;
      event.preventDefault();
      const id = ++run.current;
      setSeconds(0);
      setPhase("waking");
      (async () => {
        try {
          let state = await waker("/status");
          if (state === "asleep") state = await waker("/wake", "POST");
          while (run.current === id && state !== "awake") {
            await new Promise((resolve) => setTimeout(resolve, POLL_MS));
            state = await waker("/status");
          }
          if (run.current !== id) return; // closed by the visitor
          window.location.assign(demo); // the app has its own waiting screen for the services that start after the database
        } catch {
          if (run.current === id) setPhase("failed");
        }
      })();
    };

    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  useEffect(() => {
    if (phase !== "waking") return;
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  if (phase === "idle") return null;
  const close = () => {
    run.current++;
    setPhase("idle");
  };
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

  return (
    <div role="status" aria-live="polite" className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-md border-2 border-ink bg-white p-4 text-ink shadow-[6px_6px_0_0_var(--ink)]">
      <button type="button" onClick={close} aria-label="Close" className="absolute right-2 top-2 inline-flex min-h-11 min-w-11 items-center justify-center hover:bg-ink hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">
        <X size={18} aria-hidden />
      </button>
      {phase === "waking" ? (
        <>
          <p className="flex items-center gap-2 pr-10 font-display text-lg font-bold">
            <CircleNotch size={20} className="animate-spin motion-reduce:animate-none" aria-hidden />
            Waking the demo up
          </p>
          <p className="mt-1 text-sm">It sleeps when nobody uses it, to save resources. It takes 1 to 2 minutes; the app opens by itself. Elapsed: {clock}</p>
        </>
      ) : (
        <>
          <p className="pr-10 font-display text-lg font-bold">The demo could not be woken</p>
          <p className="mt-1 text-sm">
            <a className="underline" href={LINKS.demo}>Open the app anyway</a>
            {" "}(its own page keeps trying) or try again in a minute.
          </p>
        </>
      )}
    </div>
  );
}
