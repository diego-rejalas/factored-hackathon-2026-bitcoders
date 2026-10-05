import type { Metadata } from "next";
import localFont from "next/font/local";

import { Motion } from "@/components/site/motion-provider";

import "./globals.css";

const grotesk = localFont({
  variable: "--font-grotesk",
  display: "swap",
  src: [
    { path: "../fonts/inter-tight-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../fonts/inter-tight-latin-500-normal.woff2", weight: "500", style: "normal" },
    { path: "../fonts/inter-tight-latin-600-normal.woff2", weight: "600", style: "normal" },
  ],
});

const bricolage = localFont({
  variable: "--font-bricolage",
  display: "swap",
  src: [{ path: "../fonts/bricolage-grotesque-latin-700-normal.woff2", weight: "700", style: "normal" }],
});

const mono = localFont({
  variable: "--font-mono-body",
  display: "swap",
  src: [
    { path: "../fonts/ibm-plex-mono-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../fonts/ibm-plex-mono-latin-500-normal.woff2", weight: "500", style: "normal" },
    { path: "../fonts/ibm-plex-mono-latin-600-normal.woff2", weight: "600", style: "normal" },
  ],
});

const pixel = localFont({
  variable: "--font-pixel",
  display: "swap",
  src: [{ path: "../fonts/vt323-latin-400-normal.woff2", weight: "400", style: "normal" }],
});

export const metadata: Metadata = {
  title: "LATAM Bank dispute assistant | bitcoders",
  description:
    "A dispute assistant that resolves the safe cases in seconds and hands the rest to a person with the case ready. Team bitcoders, Factored AI and Data Hackathon 2026.",
  openGraph: {
    title: "Fast where it is safe, human where it matters.",
    description: "A dispute assistant for LATAM Bank, in Spanish and Portuguese. Team bitcoders.",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${grotesk.variable} ${mono.variable} ${pixel.variable} ${bricolage.variable}`}>
      <body className="font-sans">
        <Motion>{children}</Motion>
      </body>
    </html>
  );
}
