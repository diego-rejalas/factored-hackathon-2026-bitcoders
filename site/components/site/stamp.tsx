"use client";

import { motion } from "motion/react";

// The one moment of motion on the page: the decision lands like a rubber stamp. It plays when the page opens and
// again each time the decision changes, because that is the change the reader just caused. Reduced motion shows it still.
export function Stamp({ children, tone, id, small = false }: { children: string; tone: "ok" | "ask" | "person"; id: string; small?: boolean }) {
  const color = tone === "ok" ? "text-ok border-ok" : tone === "ask" ? "text-ink border-ink" : "text-warn border-warn";
  return (
    <motion.div
      key={id}
      initial={{ opacity: 0, scale: 1.7, rotate: -10 }}
      animate={{ opacity: 1, scale: 1, rotate: -5 }}
      transition={{ type: "spring", stiffness: 320, damping: 20 }}
      className={`inline-block border-[3px] font-mono font-semibold uppercase tracking-wide ${small ? "px-2 py-0.5 text-sm" : "px-4 py-2 text-lg md:text-xl"} ${color}`}
    >
      {children}
    </motion.div>
  );
}
