/** @type {import('next').NextConfig} */
const nextConfig = {
  // Cloud Run (and any container) runs the standalone server: no node_modules
  // needed at runtime, PORT is respected.
  output: "standalone",
};

export default nextConfig;
