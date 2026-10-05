"use client";

import Image, { type StaticImageData } from "next/image";
import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";

type Step = { title: string; text: string; image: StaticImageData; alt: string };

const frame = "overflow-hidden rounded-2xl border border-border bg-card shadow-frame";

// One screen stays in place while the steps beside it scroll by, so the story and the product are read together.
// On a phone each step carries its own screen instead.
export function Walkthrough({ steps }: { steps: Step[] }) {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.step));
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <div className="grid gap-10 md:grid-cols-[0.8fr_1.2fr] md:gap-16">
      <ol className="grid">
        {steps.map((s, i) => (
          <li
            key={s.title}
            data-step={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            className="flex flex-col justify-center gap-5 py-6 md:min-h-[70dvh]"
          >
            <div>
              <h3 className={`text-2xl font-semibold tracking-tight transition-colors md:text-3xl ${active === i ? "text-foreground" : "text-muted-foreground"}`}>{s.title}</h3>
              <p className="mt-3 max-w-[26rem] text-lg text-muted-foreground">{s.text}</p>
            </div>
            <div className={`${frame} md:hidden`}>
              <Image src={s.image} alt={s.alt} className="w-full" />
            </div>
          </li>
        ))}
      </ol>
      <div className="relative hidden md:block">
        <div className="sticky top-24 h-[min(34rem,calc(100dvh-8rem))]">
          {steps.map((s, i) => (
            <motion.div
              key={s.title}
              className={`${frame} absolute inset-x-0 top-0`}
              initial={false}
              animate={{ opacity: active === i ? 1 : 0, y: active === i ? 0 : 14 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              aria-hidden={active !== i}
            >
              <Image src={s.image} alt={s.alt} className="w-full" />
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
