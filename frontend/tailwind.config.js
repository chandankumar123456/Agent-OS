/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#F2F2F2',
        surface: '#FFFFFF',
        primary: {
          DEFAULT: '#FF6B00',
          dark: '#CC5500',
        },
        secondary: {
          DEFAULT: '#4ECDC4',
          dark: '#3DBAB1',
        },
        accent: {
          yellow: '#FFE66D',
          pink: '#FF80AB',
          purple: '#B388FF',
          mint: '#95E1D3',
        },
        primaryText: '#000000',
        secondaryText: '#4A4A5A',
        outline: '#000000',
      },
      fontFamily: {
        pixel: ['"Press Start 2P"', 'monospace'],
        retro: ['"VT323"', 'monospace'],
      },
      borderWidth: {
        '4': '4px',
        '6': '6px',
        '8': '8px',
      },
      borderRadius: {
        'none': '0',
      },
      boxShadow: {
        'pixel': '4px 4px 0px 0px #000000',
        'pixel-sm': '2px 2px 0px 0px #000000',
        'pixel-lg': '8px 8px 0px 0px #000000',
      }
    },
  },
  plugins: [],
}
