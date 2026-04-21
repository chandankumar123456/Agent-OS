/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#131314',
        surface: '#131314',
        'surface-low': '#1c1b1c',
        'surface-high': '#2a2a2b',
        'surface-highest': '#353436',
        'surface-lowest': '#0e0e0f',
        primaryText: '#e5e2e3',
        secondaryText: '#bac9cc',
        primary: '#c3f5ff',
        'primary-container': '#00e5ff',
        outline: '#3b494c',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      boxShadow: {
        'glow-cyan': '0 0 40px rgba(0, 218, 243, 0.04)',
      }
    },
  },
  plugins: [],
}
