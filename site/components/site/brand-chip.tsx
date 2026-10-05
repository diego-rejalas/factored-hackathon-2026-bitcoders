"use client";

import Image, { type StaticImageData } from "next/image";
import { useEffect, useState } from "react";

// The brand tab at the top left takes the colour of the section under it, so it melts into the page and only the name
// stays. Each section says its own colour with `data-tone`.
export function BrandChip({ logo }: { logo: StaticImageData }) {
  const [tone, setTone] = useState("lilac");
  useEffect(() => {
    const els = document.querySelectorAll<HTMLElement>("[data-tone]");
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setTone((e.target as HTMLElement).dataset.tone ?? "lilac");
      },
      { rootMargin: "-8% 0px -88% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
  return (
    <a
      href="#top"
      style={{ backgroundColor: `var(--${tone})` }}
      className="flex min-h-11 items-center gap-2 px-3 text-[1.05rem] font-semibold transition-colors duration-500 motion-reduce:transition-none focus-visible:outline focus-visible:outline-2"
    >
      <Image src={logo} alt="" width={26} height={26} className="bg-white" />
      LATAM Bank
    </a>
  );
}
