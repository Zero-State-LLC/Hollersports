import type { NextConfig } from "next";

const apiOrigin = process.env.HOLLER_API_ORIGIN ?? "http://127.0.0.1:8000";
const isGitHubPages = process.env.GITHUB_PAGES === "true";
const repositoryName = process.env.GITHUB_REPOSITORY?.split("/")[1] ?? "Hollersports";
const basePath = isGitHubPages ? `/${repositoryName}` : "";

const nextConfig: NextConfig = {
  // The monorepo has lockfiles above this package. Pin tracing here so Next
  // does not infer an unrelated workspace root during local or Pages builds.
  outputFileTracingRoot: process.cwd(),
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
