/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#07111f',
        surface: '#0c1b2e',
        elevated: '#12243c',
        panel: '#0c1b2e',
        line: '#1e3a5c',
        accent: '#3ec6ff',
        mint: '#5dffc4',
        gold: '#f5c15c',
        ink: '#e8f1fa',
        muted: '#8aa0b8',
        danger: '#ff6b7a',
      },
      fontFamily: {
        display: ['Outfit', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['IBM Plex Sans', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        card: '20px',
        pill: '999px',
      },
      boxShadow: {
        glow: '0 0 40px rgba(62,198,255,0.18)',
        card: '0 12px 40px rgba(0,0,0,0.35)',
      },
    },
  },
  plugins: [],
};
