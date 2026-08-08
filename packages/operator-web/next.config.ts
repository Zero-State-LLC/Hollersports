import type { NextConfig } from "next";

const apiOrigin = process.env.HOLLER_API_ORIGIN ?? "http://127.0.0.1:8000";
const isGitHubPages = process.env.GITHUB_PAGES === "true";
const repositoryName = process.env.GITHUB_REPOSITORY?.split("/")[1] ?? "Hollersports";
const basePath = isGitHubPages ? `/${repositoryName}` : "";

const nextConfig: NextConfig = {
  ...(isGitHubPages
    ? {
        output: "export" as const,
        basePath,
        assetPrefix: basePath,
        trailingSlash: true,
        images: { unoptimized: true },
      }
    : {}),
  ...(!isGitHubPages
    ? {
        async rewrites() {
          return [
            {
              source: "/v1/:path*",
              destination: `${apiOrigin}/v1/:path*`,
            },
          ];
        },
      }
    : {}),
};

export default nextConfig;
