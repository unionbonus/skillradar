/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#0F1419',
        panel: '#1A2029',
        line: '#2D3748',
        accent: '#4F8CFF',
        success: '#00C48C',
        danger: '#FF6B6B',
        muted: '#94A3B8',
        faint: '#64748B',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
      },
      borderRadius: {
        card: '12px',
      },
      boxShadow: {
        card: '0 4px 12px rgba(0,0,0,0.3)',
      },
    },
  },
  plugins: [],
};
