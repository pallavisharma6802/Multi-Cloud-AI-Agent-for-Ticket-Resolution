import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        // Light workspace: white content area, dark navy sidebar (kept dark
        // for the same reason real support-tool dashboards do it -- a fixed
        // nav rail reads calmer dark while the working content stays light).
        // Azure blue primary accent, vermilion orange secondary, both now
        // tuned as light-mode chip/text pairs (light fill + dark-enough text
        // for contrast on white) instead of the dark-mode dark-fill pairs.
        canvas: "#f3f5f9",
        surface: "#ffffff",
        ink: {
          DEFAULT: "#1a2436",
          soft: "#64748b",
          faint: "#94a3b8",
        },
        line: "#e2e8f0",
        brand: {
          50: "#eaf4fb",
          100: "#d3e9f7",
          500: "#329dd2",
          600: "#2b87b8",
          700: "#1f6b93",
          900: "#0f1a2e",
        },
        teal: {
          100: "#fde8e0",
          400: "#ff7a52",
          500: "#c2410c",
        },
        priority: {
          low: "#0891b2",
          medium: "#b45309",
          high: "#c2410c",
          urgent: "#dc2626",
        },
        // Extra accent family so sections of the app (sidebar nav, step
        // flows, category bars) can each carry their own color instead of
        // the whole site reading as one blue wash.
        accent: {
          purple: { 50: "#f3effe", 500: "#8b5cf6", 700: "#6d28d9" },
          teal: { 50: "#ecfdf5", 500: "#10b981", 700: "#047857" },
          orange: { 50: "#fff7ed", 500: "#f97316", 700: "#c2410c" },
          pink: { 50: "#fdf2f8", 500: "#ec4899", 700: "#be185d" },
          yellow: { 50: "#fefce8", 500: "#eab308", 700: "#a16207" },
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
        card: "0 1px 2px rgba(15,23,42,0.04), 0 8px 24px rgba(15,23,42,0.08)",
        glow: "0 0 0 1px rgba(50,157,210,0.18), 0 10px 24px rgba(50,157,210,0.16)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #329dd2 0%, #1f6b93 55%, #0f1a2e 100%)",
        "teal-gradient": "linear-gradient(135deg, #ff7a52 0%, #c2410c 100%)",
      },
    },
  },
  plugins: [],
};
export default config;
