const nextConfig = {
  images: { unoptimized: true },
  experimental: {
    serverActions: {
      bodySizeLimit: "4gb",
    },
  },
  // Proxy: /api/v1/* → FastAPI em localhost:8000
  async rewrites() {
    return [
      {
        source:      "/api/v1/:path*",
        destination: "http://localhost:8000/:path*",
      },
    ];
  },
};

export default nextConfig;
