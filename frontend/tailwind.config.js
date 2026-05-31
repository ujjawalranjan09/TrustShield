/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#111827',
          light: '#1e293b',
          lighter: '#334155',
        },
        danger: {
          DEFAULT: '#ef4444',
          dim: '#7f1d1d',
        },
        warning: {
          DEFAULT: '#f97316',
          dim: '#7c2d12',
        },
        success: {
          DEFAULT: '#22c55e',
          dim: '#14532d',
        },
        info: {
          DEFAULT: '#3b82f6',
          dim: '#1e3a5f',
        },
        accent: {
          purple: '#a855f7',
        },
      },
      keyframes: {
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in-up': 'fade-in-up 0.4s ease-out',
      },
    },
  },
  plugins: [],
}
