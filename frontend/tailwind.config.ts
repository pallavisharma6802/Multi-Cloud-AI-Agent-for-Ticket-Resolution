import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        // Resolve identity: onyx black, electric indigo, tropical mint (accent only).
        canvas: "#01010d",
        surface: "#0d0c1a",
        ink: {
          DEFAULT: "#f3f2fb",
          soft: "#a7a4c7",
          faint: "#6b6890",
        },
        line: "#201e36",
        brand: {
          50: "#1c1542",
          100: "#2a1f63",
          500: "#6331fb",
          600: "#7c4dff",
          700: "#4a1fd1",
          900: "#0a0718",
        },
        teal: {
          100: "#0f3a2c",
          400: "#4ddea0",
          500: "#88f9c0",
        },
        priority: {
          low: "#88f9c0",
          medium: "#f5b942",
          high: "#ff8a4c",
          urgent: "#ff5c72",
        },
      },
      // Site-wide type bump -- every text-xs/sm/base/etc now resolves bigger.
      // Fixes "font is too small" without touching every className.
      fontSize: {
        xs: ["13px", { lineHeight: "1.5" }],
        sm: ["15px", { lineHeight: "1.6" }],
        base: ["16px", { lineHeight: "1.65" }],
        lg: ["19px", { lineHeight: "1.6" }],
        xl: ["22px", { lineHeight: "1.5" }],
        "2xl": ["26px", { lineHeight: "1.35" }],
        "3xl": ["33px", { lineHeight: "1.25" }],
        "4xl": ["42px", { lineHeight: "1.15" }],
      },
      borderRadius: {
        xl: "14px",
        "2xl": "18px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.3), 0 10px 30px rgba(0,0,0,0.4)",
        glow: "0 0 0 1px rgba(99,49,251,0.25), 0 12px 32px rgba(99,49,251,0.22)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #6331fb 0%, #4a1fd1 55%, #0a0718 100%)",
        "teal-gradient": "linear-gradient(135deg, #88f9c0 0%, #4ddea0 100%)",
      },
    },
  },
  plugins: [],
};
export default config;
