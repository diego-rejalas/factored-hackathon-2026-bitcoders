"use client";

import { CaretLeft, CaretRight, DownloadSimple } from "@phosphor-icons/react";
import Image, { type StaticImageData } from "next/image";
import { useState } from "react";

import { Window } from "@/components/site/window";
import { Zoom } from "@/components/site/zoom";

type Slide = { src: StaticImageData; title: string };
const btn = "grid min-h-11 min-w-11 place-items-center border-2 border-ink bg-white px-2 hover:bg-cyan focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-40";

// The six slides of the deck, as pictures, with the arrow keys and a strip of thumbnails. Click a slide to open it large.
export function SlideViewer({ slides, deckHref, size }: { slides: Slide[]; deckHref: string; size: string }) {
  const [i, setI] = useState(0);
  const go = (n: number) => setI(Math.min(slides.length - 1, Math.max(0, n)));
  const s = slides[i];
  return (
    <Window title="slides.app" tone="white">
      <div
        role="group"
        aria-roledescription="carousel"
        aria-label="The pitch slides"
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") go(i + 1);
          if (e.key === "ArrowLeft") go(i - 1);
        }}
      >
        <Zoom key={i} src={s.src} alt={`Slide ${i + 1} of ${slides.length}: ${s.title}`} title={`slide ${i + 1}.png`} sizes="(min-width: 1024px) 520px, 90vw" />
        <div className="mt-3 flex items-center gap-2">
          <button type="button" onClick={() => go(i - 1)} disabled={i === 0} aria-label="Previous slide" className={btn}>
            <CaretLeft size={22} weight="bold" aria-hidden />
          </button>
          <p className="min-w-0 flex-1 text-center" aria-live="polite">
            <span className="font-mono text-sm tabular-nums">
              {i + 1} / {slides.length}
            </span>
            <span className="block truncate text-sm font-medium">{s.title}</span>
          </p>
          <button type="button" onClick={() => go(i + 1)} disabled={i === slides.length - 1} aria-label="Next slide" className={btn}>
            <CaretRight size={22} weight="bold" aria-hidden />
          </button>
        </div>
        <ul className="mt-3 grid grid-cols-6 gap-1.5">
          {slides.map((sl, k) => (
            <li key={sl.title}>
              <button
                type="button"
                onClick={() => setI(k)}
                aria-label={`Go to slide ${k + 1}: ${sl.title}`}
                aria-current={k === i}
                className={`block min-h-11 w-full border-2 ${k === i ? "border-ink shadow-[3px_3px_0_var(--ink)]" : "border-ink/40 hover:border-ink"} focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2`}
              >
                <Image src={sl.src} alt="" sizes="90px" className="h-auto w-full" />
              </button>
            </li>
          ))}
        </ul>
      </div>
      <a href={deckHref} download className="mt-3 inline-flex min-h-11 items-center gap-2 font-mono text-sm underline underline-offset-4 hover:bg-ink hover:text-white focus-visible:outline focus-visible:outline-2">
        <DownloadSimple size={18} aria-hidden />
        Download the slides, .pptx ({size})
      </a>
    </Window>
  );
}
