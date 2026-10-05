"use client";

import { ArrowDown, Robot } from "@phosphor-icons/react";
import { motion, motionValue, useReducedMotion } from "motion/react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Stamp } from "@/components/site/stamp";
import { Window } from "@/components/site/window";
import { decide, ORDER, type AgentId, type Decision, type Matches, type Status } from "@/lib/policy";

type Lang = "es" | "pt";
type Preset = { id: string; status: Status; amount: number; matches: Matches; fraud: boolean; es: string; pt: string };

// Example messages. They are not parsed: each one is paired with the charge behind it, so the Judge has facts to decide on.
const PRESETS: Preset[] = [
  { id: "reversed", status: "Reversed", amount: 389.87, matches: "one", fraud: false, es: "No reconozco el cobro de 389,87 USD en Moda Express.", pt: "Não reconheço a cobrança de 389,87 USD na Moda Express." },
  { id: "declined", status: "Declined", amount: 38.9, matches: "one", fraud: false, es: "Vi un intento de cobro de 38,90 USD que no hice yo, ¿se cobró?", pt: "Vi uma tentativa de cobrança de 38,90 USD que não fui eu, foi cobrada?" },
  { id: "approved", status: "Approved", amount: 71.3, matches: "one", fraud: false, es: "No reconozco el cobro de 71,30 USD en Taquería La Esquina.", pt: "Não reconheço a cobrança de 71,30 USD na Taquería La Esquina." },
  { id: "large", status: "Reversed", amount: 512, matches: "one", fraud: false, es: "No reconozco un cobro de 512 USD que ya me revirtieron.", pt: "Não reconheço uma cobrança de 512 USD que já foi revertida." },
  { id: "several", status: "Declined", amount: 120, matches: "several", fraud: false, es: "Me cobraron algo de una tienda y no recuerdo cuál.", pt: "Me cobraram algo de uma loja e não lembro qual." },
  { id: "none", status: "Declined", amount: 0, matches: "none", fraud: false, es: "No reconozco un cobro de 999 USD en Ferretería Sur.", pt: "Não reconheço uma cobrança de 999 USD na Ferretaria Sul." },
  { id: "fraud", status: "Approved", amount: 120, matches: "one", fraud: true, es: "Alguien usó mi tarjeta sin permiso, creo que me la robaron.", pt: "Alguém usou meu cartão sem permissão, acho que roubaram meu cartão." },
];

const LANGS: { id: Lang; label: string }[] = [
  { id: "es", label: "Español" },
  { id: "pt", label: "Português" },
];

const chip = "inline-flex min-h-11 items-center justify-center rounded-none border-2 px-4 font-mono text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2";

// A reply written for this demo, not produced by the model. It says what the real reply would say in each case.
function replyFor(d: Decision, p: Preset, lang: Lang): string {
  if (d.outcome === "resolves") {
    const rev = p.status === "Reversed";
    return lang === "es"
      ? rev ? "Ese cobro ya fue revertido y el dinero volvió a tu cuenta. Dejé el caso registrado." : "Ese cobro fue rechazado, así que no se te cargó nada. Dejé el caso registrado."
      : rev ? "Essa cobrança já foi revertida e o dinheiro voltou para a sua conta. Deixei o caso registrado." : "Essa cobrança foi recusada, então nada foi cobrado de você. Deixei o caso registrado.";
  }
  if (d.outcome === "asks") {
    return lang === "es" ? "¿A cuál de estos cobros te refieres? Cuéntame el comercio o el monto." : "A qual destas cobranças você se refere? Me diga o comércio ou o valor.";
  }
  return lang === "es" ? "Este caso necesita revisión humana. Una persona del banco lo revisará contigo." : "Este caso precisa de revisão humana. Uma pessoa do banco vai revisá-lo com você.";
}

type Kind = "model" | "code" | "backend";
const kindBg = { model: "bg-lilac", code: "bg-white", backend: "bg-win" } as const;
const kindTone = { model: "lilac", code: "white", backend: "win" } as const;

const robots: Record<AgentId, { name: string; kind: Kind; reads: string; writes: string; cannot: string }> = {
  understand: { name: "Reader", kind: "model", reads: "The customer's message.", writes: "A guess of the intent, with a confidence.", cannot: "It reads. It cannot decide or close anything." },
  decide: { name: "Judge", kind: "code", reads: "Fraud flag, matching charges, status and amount.", writes: "The route: act, escalate or respond.", cannot: "Plain code. No model is involved, and no prompt can change it." },
  act: { name: "Clerk", kind: "backend", reads: "The charge the customer chose.", writes: "Opens the case in the bank's records.", cannot: "Only the backend writes to the bank's records." },
  verify: { name: "Checker", kind: "backend", reads: "The case it just opened.", writes: "Closes it, or sends it to a person if anything fails.", cannot: "Closed means a state the backend verified." },
  escalate: { name: "Courier", kind: "code", reads: "The facts, the rule that applied and the trace.", writes: "The handoff for the specialist.", cannot: "It does not resolve anything. A person decides." },
  respond: { name: "Speaker", kind: "model", reads: "The verified facts.", writes: "The reply, in the customer's language.", cannot: "Its draft is checked against the facts before it goes out." },
};

function say(id: AgentId, d: Decision, lang: Lang): string {
  const language = lang === "es" ? "Spanish" : "Portuguese";
  switch (id) {
    case "understand":
      return `${language}. ${d.fraud ? "Intent: a fraud report." : "Intent: a dispute about a charge."}`;
    case "decide":
      return d.short;
    case "act":
      return "Opens the case through the backend.";
    case "verify":
      return "Rereads the case. The backend closes it.";
    case "escalate":
      return "Builds the handoff for the specialist.";
    case "respond":
      return d.outcome === "resolves" ? "Tells the customer it is closed." : d.outcome === "asks" ? "Asks which charge." : "Says a person will review it.";
  }
}

// Where each robot sits on the canvas, as a share of its width (left) and in pixels (top).
const SPOT: Record<AgentId, { left: number; top: number }> = {
  understand: { left: 0, top: 182 },
  decide: { left: 20.75, top: 182 },
  act: { left: 41.5, top: 0 },
  verify: { left: 62.25, top: 0 },
  escalate: { left: 41.5, top: 364 },
  respond: { left: 83, top: 182 },
};
const NODE_W = 17; // percent of the canvas
const NODE_H = 176;
const CANVAS_H = 540;
// The wires are the edges of the LangGraph in agent/app/graph.py. verify to escalate is the one that never lights up in
// this demo, because nothing here can make the backend's verification fail; it is drawn so the diagram stays complete.
type Edge = { a: AgentId; b: AgentId; vertical?: boolean };
const EDGES: Edge[] = [
  { a: "understand", b: "decide" },
  { a: "decide", b: "act" },
  { a: "act", b: "verify" },
  { a: "verify", b: "respond" },
  { a: "decide", b: "escalate" },
  { a: "escalate", b: "respond" },
  { a: "decide", b: "respond" },
  { a: "verify", b: "escalate", vertical: true },
];

const outcomeBg = { resolves: "bg-mint", asks: "bg-butter", person: "bg-coral" } as const;

type View = { reached: boolean; active: boolean; skipped: boolean };

function Card({ id, d, view, selected, onSelect, status, lang }: { id: AgentId; d: Decision; view: View; selected: boolean; onSelect: () => void; status: string; lang: Lang }) {
  const r = robots[id];
  const onPath = d.path.includes(id);
  const tone = id === "respond" && view.reached ? ({ resolves: "mint", asks: "butter", person: "coral" } as const)[d.outcome] : kindTone[r.kind];
  const text = !view.reached ? (view.active ? "Working..." : "Waiting.") : view.skipped ? "Skipped on this path." : say(id, d, lang);
  const tn = d.outcome === "resolves" ? "ok" : d.outcome === "asks" ? "ask" : "person";
  return (
    <Window title={`${ORDER.indexOf(id) + 1} ${id}.agent`} tone={id === "decide" ? "white" : tone} compact className="h-full overflow-hidden">
      <div className="flex items-center gap-2">
        <motion.button
          type="button"
          aria-pressed={selected}
          aria-label={`${r.name}, the ${id} agent. Show what it does.`}
          onClick={onSelect}
          animate={view.active ? { y: [0, -5, 0], rotate: [0, -6, 6, 0] } : { y: 0, rotate: 0 }}
          transition={view.active ? { duration: 0.7, repeat: Infinity } : { duration: 0.2 }}
          className={`grid size-11 shrink-0 place-items-center border-2 border-ink ${kindBg[r.kind]} ${selected ? "shadow-[3px_3px_0_var(--ink)]" : ""} focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2`}
        >
          <Robot size={28} weight={view.reached && onPath ? "fill" : "regular"} aria-hidden />
        </motion.button>
        <div className="min-w-0">
          <p className="font-semibold leading-tight">{r.name}</p>
          <p className="font-mono text-xs">{r.kind}</p>
        </div>
      </div>
      {id === "respond" && view.reached ? null : id === "decide" && view.reached && onPath ? (
        <p className={`mt-2 border-2 border-ink p-1.5 text-[0.8rem] font-medium leading-snug ${outcomeBg[d.outcome]}`}>{text}</p>
      ) : (
        <p className="mt-2 text-[0.8rem] font-medium leading-snug">{text}</p>
      )}
      {id === "respond" && view.reached && (
        <div className="mt-3 inline-block border-2 border-ink bg-white p-1.5">
          <Stamp tone={tn} id={status} small>
            {d.stamp}
          </Stamp>
        </div>
      )}
    </Window>
  );
}

export function Agents() {
  const [lang, setLang] = useState<Lang>("es");
  const [presetId, setPresetId] = useState(PRESETS[0].id);
  const [phase, setPhase] = useState<"idle" | "running" | "done">("idle");
  const [step, setStep] = useState(0);
  const [runs, setRuns] = useState(0);
  const [selected, setSelected] = useState<AgentId>("understand");
  const [wide, setWide] = useState(false);
  const [width, setWidth] = useState(0);
  const [, tick] = useState(0);
  const canvas = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const [mv] = useState(() => Object.fromEntries(ORDER.map((id) => [id, { x: motionValue(0), y: motionValue(0) }])) as Record<AgentId, { x: ReturnType<typeof motionValue<number>>; y: ReturnType<typeof motionValue<number>> }>);
  const preset = PRESETS.find((p) => p.id === presetId) ?? PRESETS[0];
  const d = decide({ status: preset.status, amount: preset.amount, matches: preset.matches, fraud: preset.fraud });
  const dRef = useRef(d);
  dRef.current = d;
  const key = `${presetId}-${runs}`;

  useEffect(() => {
    const q = window.matchMedia("(min-width: 1024px)");
    const sync = () => setWide(q.matches);
    sync();
    q.addEventListener("change", sync);
    return () => q.removeEventListener("change", sync);
  }, []);

  useLayoutEffect(() => {
    if (!wide || !canvas.current) return;
    const el = canvas.current;
    setWidth(el.clientWidth);
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, [wide]);

  // Send walks the robots one by one. The robot at work is also the selected one, so the panel below follows the case.
  useEffect(() => {
    if (runs === 0) return;
    if (reduce) {
      setStep(ORDER.length);
      setPhase("done");
      setSelected("respond");
      return;
    }
    setPhase("running");
    setStep(0);
    setSelected("understand");
    let i = 0;
    let timer: ReturnType<typeof setTimeout>;
    const next = () => {
      const delay = dRef.current.path.includes(ORDER[i]) ? 700 : 140;
      timer = setTimeout(() => {
        i += 1;
        setStep(i);
        if (i < ORDER.length) {
          if (dRef.current.path.includes(ORDER[i])) setSelected(ORDER[i]);
          next();
        } else {
          setPhase("done");
        }
      }, delay);
    };
    next();
    return () => clearTimeout(timer);
  }, [runs, reduce]);

  const choose = (fn: () => void) => {
    fn();
    setPhase("idle");
    setStep(0);
  };

  const done = phase === "done";
  const viewOf = (id: AgentId): View => {
    const i = ORDER.indexOf(id);
    const reached = phase !== "idle" && i < step;
    return { reached, active: phase === "running" && i === step, skipped: reached && !d.path.includes(id) };
  };

  const nodeW = (width * NODE_W) / 100;
  const at = (id: AgentId) => ({ x: (width * SPOT[id].left) / 100 + mv[id].x.get(), y: SPOT[id].top + mv[id].y.get() });
  const consecutive = (a: AgentId, b: AgentId) => d.path.some((p, i) => p === a && d.path[i + 1] === b);

  const sel = robots[selected];
  const message = preset[lang];

  return (
    <div className="grid gap-7">
      <Window title="chat.app" tone="white">
        <div className="grid gap-5 lg:grid-cols-[1.25fr_1fr]">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="font-semibold" id="msg-label">Pick a message</p>
              <div role="radiogroup" aria-label="Language" className="flex gap-1">
                {LANGS.map((l) => (
                  <button
                    key={l.id}
                    type="button"
                    role="radio"
                    aria-checked={lang === l.id}
                    onClick={() => choose(() => setLang(l.id))}
                    className={`${chip} ${lang === l.id ? "border-foreground bg-foreground text-background" : "border-foreground bg-white hover:bg-cyan"}`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
            </div>
            <div role="radiogroup" aria-labelledby="msg-label" className="mt-3 grid gap-2">
              {PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  role="radio"
                  aria-checked={presetId === p.id}
                  lang={lang}
                  onClick={() => choose(() => setPresetId(p.id))}
                  className={`min-h-11 border-2 px-3 py-2 text-left text-[0.95rem] font-medium leading-snug transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${presetId === p.id ? "border-foreground bg-cyan" : "border-foreground bg-white hover:bg-muted"}`}
                >
                  {p[lang]}
                </button>
              ))}
            </div>
          </div>

          <div className="flex min-h-[18rem] flex-col border-2 border-ink bg-muted p-3">
            <div className="grid flex-1 content-start gap-3" aria-live="polite">
              {phase === "idle" ? (
                <p className="font-mono text-sm text-muted-foreground">Pick a message and press Send. The robots answer here.</p>
              ) : (
                <>
                  <p lang={lang} className="max-w-[88%] justify-self-end border-2 border-ink bg-cyan px-3 py-2 font-medium">{message}</p>
                  {done && (
                    <div className="max-w-[92%]">
                      <p lang={lang} className="border-2 border-ink bg-white px-3 py-2 font-medium">{replyFor(d, preset, lang)}</p>
                      <p className="mt-1 font-mono text-xs text-muted-foreground">Example reply, written for this demo.</p>
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="mt-3 flex items-center gap-2 border-t-2 border-ink pt-3">
              <p lang={lang} className="min-w-0 flex-1 truncate border-2 border-ink bg-white px-3 py-2 text-sm">{message}</p>
              <button
                type="button"
                onClick={() => {
                  setRuns((r) => r + 1);
                  stage.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
                }}
                disabled={phase === "running"}
                className={`${chip} shrink-0 border-foreground bg-foreground text-background hover:bg-cyan hover:text-foreground disabled:opacity-50`}
              >
                Send
              </button>
            </div>
          </div>
        </div>
        <p className="mt-4 text-sm text-muted-foreground">
          The messages are examples, and each one is paired with the charge behind it so the Judge has facts to decide on. The Judge is the real order of checks, written as code. The Reader and the Speaker are described, not run.
          {wide ? " Drag the robots around: the wires follow." : ""}
        </p>
      </Window>

      <div ref={stage} className="grid gap-7">
      <p className="sr-only" aria-live="polite">{done ? `${d.stamp}. ${d.reason}` : ""}</p>

      {wide ? (
        <div ref={canvas} className="relative" style={{ height: CANVAS_H }}>
          <svg className="pointer-events-none absolute inset-0 size-full overflow-visible" aria-hidden>
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill="var(--ink)" />
              </marker>
              <marker id="arrow-faint" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill="var(--ink)" fillOpacity="0.3" />
              </marker>
            </defs>
            {width > 0 &&
              EDGES.map(({ a, b, vertical }) => {
                const pa = at(a);
                const pb = at(b);
                const x1 = vertical ? pa.x + nodeW / 2 : pa.x + nodeW;
                const y1 = vertical ? pa.y + NODE_H : pa.y + NODE_H / 2;
                const x2 = vertical ? pb.x + nodeW / 2 : pb.x;
                const y2 = vertical ? pb.y : pb.y + NODE_H / 2;
                const dx = Math.max(30, Math.abs(x2 - x1) / 2);
                const dy = Math.max(30, Math.abs(y2 - y1) / 2);
                const curve = vertical ? `M${x1} ${y1} C${x1} ${y1 + dy} ${x2} ${y2 - dy} ${x2} ${y2}` : `M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`;
                const lit = consecutive(a, b) && ORDER.indexOf(b) < step;
                const flowing = consecutive(a, b) && ORDER.indexOf(b) === step && !done;
                return (
                  <path
                    key={`${a}-${b}`}
                    d={curve}
                    fill="none"
                    stroke="var(--ink)"
                    strokeOpacity={lit || flowing || (done && consecutive(a, b)) ? 1 : 0.3}
                    strokeWidth={lit || flowing || (done && consecutive(a, b)) ? 3 : 2}
                    strokeDasharray={lit || (done && consecutive(a, b)) ? undefined : "7 7"}
                    markerEnd={lit || flowing || (done && consecutive(a, b)) ? "url(#arrow)" : "url(#arrow-faint)"}
                    className={flowing ? "[animation:wire_0.6s_linear_infinite] motion-reduce:[animation:none]" : ""}
                  />
                );
              })}
          </svg>
          {ORDER.map((id) => (
            <motion.div
              key={id}
              drag
              dragMomentum={false}
              dragElastic={0.04}
              dragConstraints={canvas}
              onDrag={() => tick((n) => n + 1)}
              style={{ x: mv[id].x, y: mv[id].y, left: `${SPOT[id].left}%`, top: SPOT[id].top, width: `${NODE_W}%`, height: NODE_H, zIndex: selected === id ? 5 : 1 }}
              whileDrag={{ zIndex: 20, cursor: "grabbing" }}
              className={`absolute cursor-grab transition-opacity duration-300 motion-reduce:transition-none ${viewOf(id).skipped || (!viewOf(id).reached && !viewOf(id).active) ? "opacity-50" : ""}`}
            >
              <Card id={id} d={d} view={viewOf(id)} selected={selected === id} onSelect={() => setSelected(id)} status={key} lang={lang} />
            </motion.div>
          ))}
        </div>
      ) : (
        <ol className="grid gap-3">
          {ORDER.map((id, i) => (
            <li key={id} className={viewOf(id).skipped ? "opacity-50" : ""}>
              <Card id={id} d={d} view={viewOf(id)} selected={selected === id} onSelect={() => setSelected(id)} status={key} lang={lang} />
              {i < ORDER.length - 1 && (
                <div aria-hidden className="grid place-items-center pt-3">
                  <ArrowDown size={22} weight="bold" />
                </div>
              )}
            </li>
          ))}
        </ol>
      )}

      <Window title={`${selected}.agent`} tone={kindTone[sel.kind]}>
        <p className="font-semibold">
          {sel.name} <span className="font-mono text-sm font-normal">({sel.kind})</span>
        </p>
        <dl className="mt-2 grid gap-1 text-sm md:grid-cols-3 md:gap-6">
          <div>
            <dt className="font-mono">Reads</dt>
            <dd className="font-medium">{sel.reads}</dd>
          </div>
          <div>
            <dt className="font-mono">Writes</dt>
            <dd className="font-medium">{sel.writes}</dd>
          </div>
          <div>
            <dt className="font-mono">Cannot</dt>
            <dd className="font-medium">{sel.cannot}</dd>
          </div>
        </dl>
        {selected === "respond" && done && (
          <p lang={lang} className="mt-3 border-2 border-ink bg-white px-3 py-2 font-medium">
            {replyFor(d, preset, lang)} <span className="font-mono text-xs font-normal">Example reply.</span>
          </p>
        )}
        <p className="mt-2 font-mono text-xs">Click a robot to see what it does.</p>
      </Window>
      </div>
    </div>
  );
}
