import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        // Resolve identity: midnight ink, azure blue (primary accent),
        // vermilion orange (single secondary highlight, used sparingly).
        canvas: "#080f1b",
        surface: "#0e1726",
        ink: {
          DEFAULT: "#f2f5fa",
          soft: "#9fb0c6",
          faint: "#5f7489",
        },
        line: "#1b2840",
        brand: {
          50: "#112a3d",
          100: "#16374f",
          500: "#329dd2",
          600: "#4db2e3",
          700: "#1f6b93",
          900: "#0b2030",
        },
        teal: {
          100: "#3a1710",
          400: "#ff7a52",
          500: "#ff4c2b",
        },
        priority: {
          low: "#4db2e3",
          medium: "#f5b942",
          high: "#ff7a52",
          urgent: "#ff4c2b",
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
        card: "0 1px 2px rgba(0,0,0,0.3), 0 10px 30px rgba(0,0,0,0.4)",
        glow: "0 0 0 1px rgba(50,157,210,0.25), 0 12px 32px rgba(50,157,210,0.22)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #329dd2 0%, #1f6b93 55%, #0b2030 100%)",
        "teal-gradient": "linear-gradient(135deg, #ff7a52 0%, #ff4c2b 100%)",
      },
    },
  },
  plugins: [],
};
export default config;
