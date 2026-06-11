import type { NextConfig } from "next";

// Rewrites are compiled into the Next.js build; changing this target requires a rebuild.
const apiProxyTarget = (process.env.API_PROXY_TARGET ?? "http://localhost:5155").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` }];
  }
};

export default nextConfig;
