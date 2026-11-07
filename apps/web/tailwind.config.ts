import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17202a",
        paper: "#f7f8f5",
        moss: "#315c4c",
        line: "#dfe5df",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui"],
        display: ["var(--font-newsreader)", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
