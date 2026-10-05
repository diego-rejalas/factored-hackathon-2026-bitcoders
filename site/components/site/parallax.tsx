"use client";

import { motion, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from "motion/react";
import { useEffect, useRef, useState } from "react";

// True only after the page has mounted and the visitor asked for reduced motion. The first render always matches the
// server's HTML, so hydration stays clean.
function useCalm() {
  const reduce = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted && !!reduce;
}

// Scroll-linked movement. Every piece reads the position of its own element in the viewport, and does not move at all
// when the visitor asks for reduced motion.

// Floats up (or down) by a different amount than the page scrolls, so layers drift apart.
export function Float({ children, from = 60, to = -60, className }: { children: React.ReactNode; from?: number; to?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useCalm();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], reduce ? [0, 0] : [from, to]);
  return (
    <motion.div ref={ref} style={{ y }} className={`${/\b(absolute|fixed|sticky)\b/.test(className ?? "") ? "" : "relative "}${className ?? ""}`}>
      {children}
    </motion.div>
  );
}

// Slides in from the side and settles when it reaches the middle of the screen.
export function Drift({ children, from = 120, className }: { children: React.ReactNode; from?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useCalm();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "center center"] });
  const x = useTransform(scrollYProgress, [0, 1], reduce ? [0, 0] : [from, 0]);
  return (
    <motion.div ref={ref} style={{ x }} className={`relative ${className ?? ""}`}>
      {children}
    </motion.div>
  );
}

// Follows the pointer: the layer shifts a little against the cursor, by `depth` pixels at the edges of the window. Layers
// with different depths slide past each other. Does nothing on touch screens or with reduced motion.
export function PointerLayer({ children, depth = 20, className }: { children: React.ReactNode; depth?: number; className?: string }) {
  const calm = useCalm();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const sx = useSpring(x, { stiffness: 90, damping: 20 });
  const sy = useSpring(y, { stiffness: 90, damping: 20 });
  useEffect(() => {
    if (calm) return;
    const move = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      x.set((e.clientX / window.innerWidth - 0.5) * depth * -2);
      y.set((e.clientY / window.innerHeight - 0.5) * depth * -2);
    };
    window.addEventListener("pointermove", move);
    return () => window.removeEventListener("pointermove", move);
  }, [calm, depth, x, y]);
  return (
    <motion.div style={{ x: sx, y: sy }} className={className}>
      {children}
    </motion.div>
  );
}
