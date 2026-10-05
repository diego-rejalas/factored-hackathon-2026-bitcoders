// The links that are not final yet. Fill one in and every button that uses it turns on.
// An empty one shows "Soon" and cannot be clicked.
export const LINKS = {
  video: "", // the pitch video (YouTube, Vimeo, Drive...)
  pdf: "", // the slides, for example "/bitcoders-pitch.pdf" after putting the file in public/
  diego: "", // https://www.linkedin.com/in/...
  felix: "", // https://www.linkedin.com/in/...
  repo: "https://github.com/diego-rejalas/factored-hackathon-2026-bitcoders",
  demo: "https://136-82-12-89.sslip.io",
} as const;

export type LinkKey = keyof typeof LINKS;
