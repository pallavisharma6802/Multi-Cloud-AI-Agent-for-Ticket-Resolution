const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${process.env.API_INTERNAL_URL || "http://backend:8000"}/:path*`,
      },
    ];
  },
  // Standalone output keeps the Docker image lean (frontend/Dockerfile
  // copies only the traced production server + deps, not the full
  // node_modules tree).
  output: "standalone",
  // Pins the workspace root to this directory -- without it, Next.js can
  // mistakenly infer an ancestor directory as the root if it finds another
  // lockfile higher up the filesystem tree (e.g. in a parent home directory
  // outside this repo), which breaks file tracing for the production build.
  outputFileTracingRoot: path.join(__dirname),
};

module.exports = nextConfig;
