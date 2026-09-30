import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Asistente bancario LATAM",
  description: "Prototipo de atención al cliente bancario con IA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
