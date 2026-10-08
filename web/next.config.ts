import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static site for Amplify Hosting / S3 + CloudFront. No server features.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: {
    root: __dirname,
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
