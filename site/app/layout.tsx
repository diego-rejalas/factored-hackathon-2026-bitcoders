import type { Metadata } from "next";
import localFont from "next/font/local";

import { Motion } from "@/components/site/motion-provider";

import "./globals.css";

const plex = localFont({
  variable: "--font-plex",
  display: "swap",
  src: [
    { path: "../fonts/ibm-plex-sans-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../fonts/ibm-plex-sans-latin-600-normal.woff2", weight: "600", style: "normal" },
    { path: "../fonts/ibm-plex-sans-latin-700-normal.woff2", weight: "700", style: "normal" },
  ],
});

export const metadata: Metadata = {
  title: "LATAM Bank dispute assistant | bitcoders",
  description:
    "A dispute assistant that resolves the safe cases in seconds and hands the rest to a person with the case ready. Team bitcoders, Factored AI and Data Hackathon 2026.",
  openGraph: {
    title: "Fast where it is safe, human where it matters.",
    description: "A dispute assistant for LATAM Bank, in Spanish and Portuguese. Team bitcoders.",
  },
  icons: { icon: "/logo.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={plex.variable}>
      <body className="font-sans">
        <Motion>{children}</Motion>
      </body>
    </html>
  );
}
