/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Paper / surfaces — warm off-white, never pure white
        paper: "#FBF8F3",
        "paper-dark": "#F5EFE4", // slightly darker warm surface for cards, sidebars
        surface: "#FFFFFF",
        "surface-sunk": "#F5EFE4", // legacy alias of paper-dark (same value)
        // Ink — warm near-black text palette
        ink: "#1F2937",
        "ink-muted": "#6B7280",
        "ink-faint": "#9CA3AF",
        // Rules / dividers
        rule: "#E5E1D6",
        "rule-strong": "#CEC6B5",
        divider: "#E5E1D6", // alias of rule
        // Accent — deep burnished amber / sienna. Warm, confident, printed.
        accent: "#8B4513",
        "accent-bg": "#F5EADF",
        "accent-hover": "#6B340F",
        // Attention — amber, for in-progress / provisional emphasis
        attention: "#B45309",
        "attention-bg": "#FEF3C7",
        // Semantic state pips (sections, plan items, etc.)
        "state-confident": "#047857", // deep green — settled
        "state-confident-bg": "#ECFDF5",
        "state-provisional": "#B45309", // amber — in progress
        "state-provisional-bg": "#FEF3C7",
        "state-blocked": "#9F1239", // rusty red — stopped
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
        prose: "70ch",
        page: "1120px",
        wide: "1000px",
        narrow: "720px",
      },
      lineHeight: {
        prose: "1.65",
      },
    },
  },
  plugins: [],
};
