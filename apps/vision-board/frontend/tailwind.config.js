/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'board-bg': '#0a0a0a',
        'card-bg': '#1a1a1a',
        'accent': '#ffd700',
        'cat-personal': '#ff6b9d',
        'cat-travel': '#00d2ff',
        'cat-career': '#00ff9d',
        'cat-wealth': '#ffd700',
        'cat-fitness': '#ff6b35',
        'cat-creative': '#bd00ff',
        'cat-home': '#7dd87d',
        'cat-food': '#ffb347',
        'cat-relationships': '#ff69b4',
        'cat-inspiration': '#666666',
      }
    },
  },
  plugins: [],
}
