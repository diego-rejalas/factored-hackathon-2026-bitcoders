"use client";

import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const KEY = "chat-theme";

/** The theme the reader picked, or null to follow the system. Shared by the sign-in page and the chat. */
export function useTheme(): [Theme | null, () => void] {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(KEY);
      if (saved === "light" || saved === "dark") setTheme(saved);
    } catch {
      /* storage can be blocked; the system theme applies */
    }
  }, []);

  const toggle = useCallback(() => {
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const effective = theme ?? (systemDark ? "dark" : "light");
    const next: Theme = effective === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* not remembered */
    }
  }, [theme]);

  return [theme, toggle];
}
