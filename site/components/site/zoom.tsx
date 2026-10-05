"use client";

import Image, { type StaticImageData } from "next/image";
import { useRef } from "react";

import { Window } from "@/components/site/window";

// A screenshot that opens large when you click it. It uses the browser's own modal dialog, so Escape closes it, focus
// stays inside while it is open, and focus returns to the screenshot afterwards.
export function Zoom({
  src,
  alt,
  title,
  sizes = "(min-width: 900px) 640px, 90vw",
  className = "",
}: {
  src: StaticImageData;
  alt: string;
  title: string;
  sizes?: string;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  return (
    <>
      <button
        type="button"
        onClick={() => ref.current?.showModal()}
        aria-label={`Open larger: ${alt}`}
        className="block w-full cursor-zoom-in border-2 border-ink focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        <Image src={src} alt="" sizes={sizes} className={`h-auto w-full ${className}`} />
      </button>
      <dialog
        ref={ref}
        aria-label={alt}
        onClick={(e) => {
          if (e.target === ref.current) ref.current?.close();
        }}
        className="m-auto max-h-[96svh] max-w-[96vw] overflow-visible bg-transparent p-0"
      >
        <Window title={title} tone="win">
          <div className="max-h-[78svh] overflow-auto">
            <Image src={src} alt={alt} sizes="94vw" className="mx-auto h-auto max-h-[76svh] w-auto max-w-full border-2 border-ink" />
          </div>
          <form method="dialog" className="mt-4 flex justify-end">
            <button type="submit" className="min-h-11 border-2 border-ink bg-ink px-5 font-mono text-sm text-white hover:bg-white hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">
              Close
            </button>
          </form>
        </Window>
      </dialog>
    </>
  );
}
