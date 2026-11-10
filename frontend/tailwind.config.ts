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
      // A previous pass over-corrected "too small" into "too big", especially
      // at the heading/stat sizes (4xl went to 42px). Pulled back down,
      // closer to Tailwind's own defaults, with just a slight bump on body
      // text (xs/sm/base) since plain defaults did read a little small.
      fontSize: {
        xs: ["12px", { lineHeight: "1.5" }],
        sm: ["13.5px", { lineHeight: "1.5" }],
        base: ["15px", { lineHeight: "1.6" }],
        lg: ["17px", { lineHeight: "1.55" }],
        xl: ["19px", { lineHeight: "1.45" }],
        "2xl": ["22px", { lineHeight: "1.3" }],
        "3xl": ["28px", { lineHeight: "1.2" }],
        "4xl": ["34px", { lineHeight: "1.1" }],
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
