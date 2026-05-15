import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  experimental: {
    typedRoutes: false,
  },
  webpack(config) {
    config.resolve.symlinks = false;
    config.cache = false;
    return config;
  },
};

export default nextConfig;
