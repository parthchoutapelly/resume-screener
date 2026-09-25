import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react()],
    define: command === 'serve' ? {
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api'),
    } : {},
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || env.VITE_API_BASE_URL,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              if (env.VITE_DISTRIBUTION_DOMAIN) {
                proxyReq.setHeader('origin', `https://${env.VITE_DISTRIBUTION_DOMAIN}`);
              } else {
                proxyReq.removeHeader('origin');
              }
            });
          },
        },
      },
    },
    build: {
      sourcemap: false,
    },
  };
});
