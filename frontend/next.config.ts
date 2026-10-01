import type { NextConfig } from "next";

const config: NextConfig = {
  // Static dbt docs (lineage graph + column catalog), see README "Documentación de datos".
  async rewrites() {
    return [{ source: "/data-docs", destination: "/data-docs/index.html" }];
  },
};

export default config;
