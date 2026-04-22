/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#FBF8F3",
        surface: "#FFFFFF",
        "surface-sunk": "#F5EFE4",
        ink: "#1F2937",
        "ink-muted": "#6B7280",
        "ink-faint": "#9CA3AF",
        rule: "#E5E1D6",
        "rule-strong": "#CEC6B5",
        accent: "#8B4513",
        "accent-bg": "#F5EADF",
        "accent-hover": "#6B340F",
        attention: "#B45309",
        "attention-bg": "#FEF3C7",
        "state-confident": "#047857",
        "state-confident-bg": "#ECFDF5",
        "state-provisional": "#78716C",
        "state-provisional-bg": "#F5F5F4",
        "state-blocked": "#9F1239",
        "state-blocked-bg": "#FFF1F2",
      },
      fontFamily: {
        serif: ['"Lora"', '"Charter"', '"Georgia"', "serif"],
        mono: ['"JetBrains Mono"', '"SF Mono"', '"Menlo"', "monospace"],
        sans: ['"Inter"', "-apple-system", "BlinkMacSystemFont", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "2px",
      },
      maxWidth: {
        prose: "68ch",
        page: "1120px",
        wide: "1000px",
        narrow: "720px",
      },
    },
  },
  plugins: [],
};
