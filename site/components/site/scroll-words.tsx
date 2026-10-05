"use client";

import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useTransform, type MotionValue } from "motion/react";

// The story is told as the reader scrolls: each word comes up as it is reached. It carries the narrative
// (the customer, the bank, the hard part) in order, and it is static for anyone who asks for less motion.
function Word({ children, range, progress, className }: { children: string; range: [number, number]; progress: MotionValue<number>; className?: string }) {
  const opacity = useTransform(progress, range, [0.2, 1]);
  return (
    <motion.span style={{ opacity }} className={className}>
      {children}{" "}
    </motion.span>
  );
}

export function ScrollWords({ parts }: { parts: { text: string; className?: string }[] }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.85", "end 0.55"] });

  const words = parts.flatMap((p) => p.text.split(" ").map((w) => ({ w, className: p.className })));
  const n = words.length;

  return (
    <p ref={ref} className="text-balance text-[clamp(1.9rem,4.6vw,3.6rem)] font-semibold leading-[1.12] tracking-[-0.02em]">
      {words.map((word, i) =>
        reduce ? (
          <span key={i} className={word.className}>{word.w}{" "}</span>
        ) : (
          <Word key={i} range={[i / n, Math.min(1, (i + 1) / n)]} progress={scrollYProgress} className={word.className}>
            {word.w}
          </Word>
        ),
      )}
    </p>
  );
}
