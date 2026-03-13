/* eslint-disable @typescript-eslint/no-require-imports */
import { type NextConfig } from "next";

import createNextIntlPlugin from "next-intl/plugin";

if (process.env.NODE_ENV === "development") {
  // Clear CLAUDECODE env so react-grab can spawn Claude Code without nested-session error
  delete process.env.CLAUDECODE;
  const { startServer } = require("@react-grab/claude-code/server");
  startServer();
}

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "app.chatvote.org",
        port: "",
        pathname: "/images/**",
      },
      {
        protocol: "https",
        hostname: "storage.googleapis.com",
        port: "",
        pathname: "/chat-vote-dev.firebasestorage.app/**",
      },
      {
        protocol: "https",
        hostname: "chatvote-public-assets.s3.fr-par.scw.cloud",
        port: "",
        pathname: "/public/**",
      },
    ],
  },
  webpack: (config: { resolve: { alias: { [key: string]: boolean } } }) => {
    config.resolve.alias.canvas = false;

    return config;
  },
};

const withBundleAnalyzer = require("@next/bundle-analyzer")({
  enabled: process.env.ANALYZE === "true",
});

const withNextIntl = createNextIntlPlugin();
export default withBundleAnalyzer(withNextIntl(nextConfig));

