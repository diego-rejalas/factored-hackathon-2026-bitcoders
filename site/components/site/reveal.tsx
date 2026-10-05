"use client";

import { motion } from "motion/react";

// Content arrives once as it enters the view, to show where the page begins a new idea. It never loops.
// <Motion> in layout.tsx sets reducedMotion="user", so people who ask for less motion get a plain fade, with no movement.
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 22 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}
