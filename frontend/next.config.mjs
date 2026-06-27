const nextConfig = {
  images: { unoptimized: true },
  // Permite uploads grandes (vídeos de câmera-armadilha podem ter vários GB)
  experimental: {
    serverActions: {
      bodySizeLimit: "4gb",
    },
  },
};

export default nextConfig;
