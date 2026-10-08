// The links that are not final yet. Fill one in and every button that uses it turns on.
// An empty one shows "Soon" and cannot be clicked.
const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

// The files themselves. The deck is served from public/. The video is not in the repository: it is served from a host
// that answers range requests, which a person needs to skip through it (a bucket, YouTube, Vimeo). Set
// NEXT_PUBLIC_VIDEO_URL when building. Without it the page says the video is not part of the build.
export const FILES = {
  video: process.env.NEXT_PUBLIC_VIDEO_URL ?? "",
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

// The waker: a service that stops the demo when nobody uses it and starts it on request. Set NEXT_PUBLIC_WAKER_URL (for
// example https://<the app>/waker) and the "Live demo" links wake the demo first and show how far it is. Empty: they go
// straight to the app.
export const WAKER_URL = (process.env.NEXT_PUBLIC_WAKER_URL ?? "").replace(/\/$/, "");

export type LinkKey = keyof typeof LINKS;
