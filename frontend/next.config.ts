import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // separate build folder for side-by-side previews (e.g. NEXT_DIST_DIR=.next-preview)
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // react-pdf ships an optional node-canvas dependency we never use in the browser
  webpack: (config) => {
    config.resolve.alias.canvas = false;
    return config;
  },
};

export default nextConfig;
