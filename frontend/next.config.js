/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
    // /api/v1/* is handled by app/api/v1/[...path] so Authorization/cookie survive.
    return [{ source: '/api/:path*', destination: `${backend}/api/:path*` }];
  },
};
module.exports = nextConfig;
