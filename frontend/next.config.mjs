/** @type {import('next').NextConfig} */
const nextConfig = {
  // Cloud Run (and any container) runs the standalone server: no node_modules
  // needed at runtime, PORT is respected.
  output: "standalone",
  // The dev server (Next 16+) writes AGENTS.md and CLAUDE.md with rules for AI assistants into the project on
  // every start. Not wanted here: they would show up as untracked files for everyone who runs it.
  agentRules: false,
};

export default nextConfig;
