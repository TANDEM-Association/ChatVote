/* eslint-disable @typescript-eslint/no-require-imports */
import { type NextConfig } from "next";

import createNextIntlPlugin from "next-intl/plugin";

const nextConfig: NextConfig = {
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
