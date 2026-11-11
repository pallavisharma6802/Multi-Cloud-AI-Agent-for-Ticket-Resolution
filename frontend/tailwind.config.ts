import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-fraunces)", "ui-serif", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        // Warm light help-desk theme: cream/white background, espresso ink,
        // gold + rose accents reserved for labels/icons/CTAs -- not washed
        // across whole surfaces.
        canvas: "#faf6f1",
        surface: "#ffffff",
        ink: {
          DEFAULT: "#241b17",
          soft: "#6b5a52",
          faint: "#9c8a81",
        },
        line: "#ece2d8",
        brand: {
          50: "rgba(203,138,46,0.08)",
          100: "rgba(203,138,46,0.14)",
          500: "#cb8a2e",
          600: "#a66f22",
          700: "#8a5c1c",
          900: "#15100d",
        },
        rose: {
          50: "rgba(214,90,120,0.08)",
          500: "#d65a78",
          700: "#b03f5c",
        },
        teal: {
          100: "rgba(203,138,46,0.14)",
          400: "#cb8a2e",
          500: "#8a5c1c",
        },
        priority: {
          low: "#22d3ee",
          medium: "#f2b84b",
          high: "#fb923c",
          urgent: "#f87171",
        },
        // Extra accent family so sections of the app (sidebar nav, step
        // flows, category bars) can each carry their own color instead of
        // the whole site reading as one gold wash.
        accent: {
          purple: { 50: "rgba(167,139,250,0.12)", 500: "#a78bfa", 700: "#c4b5fd" },
          teal: { 50: "rgba(45,212,191,0.12)", 500: "#2dd4bf", 700: "#5eead4" },
          orange: { 50: "rgba(251,146,60,0.12)", 500: "#fb923c", 700: "#fdba74" },
          pink: { 50: "rgba(231,143,163,0.12)", 500: "#e78fa3", 700: "#f3b6c4" },
          yellow: { 50: "rgba(242,184,75,0.12)", 500: "#f2b84b", 700: "#facc15" },
        },
      },
      // Site-wide type bump -- every text-xs/sm/base/etc now resolves bigger.
      // A previous pass over-corrected "too small" into "too big", especially
      // at the heading/stat sizes (4xl went to 42px). Pulled back down,
      // closer to Tailwind's own defaults, with just a slight bump on body
      // text (xs/sm/base) since plain defaults did read a little small.
      fontSize: {
        xs: ["11px", { lineHeight: "1.45" }],
        sm: ["12.5px", { lineHeight: "1.5" }],
        base: ["14px", { lineHeight: "1.55" }],
        lg: ["15.5px", { lineHeight: "1.5" }],
        xl: ["17px", { lineHeight: "1.4" }],
        "2xl": ["19px", { lineHeight: "1.3" }],
        "3xl": ["23px", { lineHeight: "1.2" }],
        "4xl": ["28px", { lineHeight: "1.15" }],
      },
      borderRadius: {
        xl: "14px",
        "2xl": "18px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(36,27,23,0.05), 0 8px 24px rgba(36,27,23,0.08)",
        glow: "0 0 0 1px rgba(203,138,46,0.25), 0 10px 24px rgba(203,138,46,0.16)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #cb8a2e 0%, #d65a78 100%)",
        "teal-gradient": "linear-gradient(135deg, #cb8a2e 0%, #a66f22 100%)",
      },
    },
  },
  plugins: [],
};
export default config;
