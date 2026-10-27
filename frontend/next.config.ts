import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  // Pages renamed in the redesign; keep old bookmarks working.
  async redirects() {
    return [
      { source: "/market", destination: "/destinations", permanent: false },
      { source: "/opportunities", destination: "/resources", permanent: false },
      { source: "/roadmap", destination: "/plan", permanent: false },
    ];
  },
  partialPrefetching: true,
  experimental: {
    agentUpgrade: "security",
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
