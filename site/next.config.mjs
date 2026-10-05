/** @type {import('next').NextConfig} */
const nextConfig = {
  // A static site: `next build` writes the whole page to out/, which any static host can serve.
  output: "export",
  images: { unoptimized: true },
  // Set NEXT_PUBLIC_BASE_PATH=/<repo> when it is served from a GitHub Pages project URL.
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",
  devIndicators: false,
  agentRules: false,
};

export default nextConfig;
