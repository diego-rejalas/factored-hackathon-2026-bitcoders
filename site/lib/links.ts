// The links that are not final yet. Fill one in and every button that uses it turns on.
// An empty one shows "Soon" and cannot be clicked.
const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

// The files themselves, served from public/. The video can move to YouTube or Vimeo later to keep the repo small.
export const FILES = {
  video: `${BASE}/bitcoders-pitch.mp4`,
  deck: `${BASE}/bitcoders-pitch.pptx`,
} as const;

export const LINKS = {
  video: "#pitch", // the player on this page
  pdf: "#pitch", // the slide viewer on this page
  diego: "https://www.linkedin.com/in/diego-rejalas",
  felix: "https://www.linkedin.com/in/f%C3%A9lix-morales-mareco-148b99150", // the accent in the profile name is percent-encoded
  repo: "https://github.com/diego-rejalas/factored-hackathon-2026-bitcoders",
  demo: process.env.NEXT_PUBLIC_DEMO_URL ?? "", // the live app; set NEXT_PUBLIC_DEMO_URL when building (see .env.example)
} as const;

export type LinkKey = keyof typeof LINKS;
