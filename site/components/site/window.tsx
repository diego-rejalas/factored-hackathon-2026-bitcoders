"use client";

import { motion } from "motion/react";

const tones = {
  win: "bg-win",
  mint: "bg-mint",
  butter: "bg-butter",
  coral: "bg-coral",
  white: "bg-white",
  lilac: "bg-lilac",
  cyan: "bg-cyan",
} as const;

// A window with a navy title bar and a hard offset shadow. With `drag`, it can be picked up and moved around inside its
// desk. That is only a way to play with the page: the content stays where it is in the document order.
export function Window({
  title,
  children,
  className = "",
  drag = false,
  tone = "win",
  compact = false,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
  drag?: boolean;
  tone?: keyof typeof tones;
  compact?: boolean;
}) {
  const Comp = drag ? motion.div : "div";
  const extra = drag ? { drag: true, dragMomentum: false, dragElastic: 0.08, whileDrag: { zIndex: 30, cursor: "grabbing" } } : {};
  return (
    <Comp {...extra} className={`window-scope relative border-2 border-ink shadow-[6px_6px_0_var(--ink)] ${tones[tone]} ${drag ? "cursor-grab" : ""} ${className}`}>
      <div className="flex items-center gap-2 bg-ink px-2 py-0.5 font-pixel text-xl leading-6 text-white">
        <span aria-hidden className="size-3 bg-cyan" />
        {title}
      </div>
      <div className={compact ? "p-3" : "p-4 md:p-5"}>{children}</div>
    </Comp>
  );
}
