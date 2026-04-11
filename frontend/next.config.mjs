/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',      // static export → served by Flask
  distDir: 'build',      // Flask serves from frontend/build/
  trailingSlash: true,
  images: { unoptimized: true },

  // Suppress build errors on JSX/ESLint during migration
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
};

export default nextConfig;
