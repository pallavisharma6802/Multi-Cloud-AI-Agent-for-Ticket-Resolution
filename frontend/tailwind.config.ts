import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        // One sans everywhere (headings included). Mono reserved for
        // badges, IDs, timestamps -- not a second display typeface.
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        // Neutral gray-scale base, white surfaces, single indigo accent.
        // Color is reserved for the primary action and status/severity --
        // not decoration.
        canvas: "#f6f7f9",
        surface: "#ffffff",
        ink: {
          DEFAULT: "#111418",
          soft: "#5b6472",
          faint: "#9aa3af",
        },
        line: "#e5e7eb",
        brand: {
          50: "rgba(79,70,229,0.06)",
          100: "rgba(79,70,229,0.12)",
          500: "#4f46e5",
          600: "#4338ca",
          700: "#3730a3",
          900: "#1e1b4b",
        },
        // Legacy token names kept so existing component code keeps working;
        // both now resolve to the same neutral/indigo system (no separate
        // rose/teal brand hues).
        rose: {
          50: "rgba(220,38,38,0.06)",
          500: "#dc2626",
          700: "#991b1b",
        },
        teal: {
          100: "rgba(22,163,74,0.12)",
          400: "#16a34a",
          500: "#15803d",
        },
        priority: {
          low: "#5b6472",
          medium: "#b45309",
          high: "#c2410c",
          urgent: "#dc2626",
        },
        // Reduced to a single functional accent family -- every section
        // uses this same indigo instead of a different hue each.
        accent: {
          purple: { 50: "rgba(79,70,229,0.06)", 500: "#4f46e5", 700: "#3730a3" },
          teal: { 50: "rgba(79,70,229,0.06)", 500: "#4f46e5", 700: "#3730a3" },
          orange: { 50: "rgba(79,70,229,0.06)", 500: "#4f46e5", 700: "#3730a3" },
          pink: { 50: "rgba(79,70,229,0.06)", 500: "#4f46e5", 700: "#3730a3" },
          yellow: { 50: "rgba(79,70,229,0.06)", 500: "#4f46e5", 700: "#3730a3" },
        },
      },
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
        xl: "10px",
        "2xl": "12px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(17,20,24,0.04), 0 1px 8px rgba(17,20,24,0.05)",
        glow: "0 0 0 1px rgba(79,70,229,0.2)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #4f46e5 0%, #4338ca 100%)",
        "teal-gradient": "linear-gradient(135deg, #4f46e5 0%, #4338ca 100%)",
      },
    },
  },
  plugins: [],
};
export default config;
