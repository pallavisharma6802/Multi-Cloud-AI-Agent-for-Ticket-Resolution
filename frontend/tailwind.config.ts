import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        // Resolve identity: cool slate, electric blue, teal.
        canvas: "#f4f7fc",
        surface: "#ffffff",
        ink: {
          DEFAULT: "#172840",
          soft: "#53657c",
          faint: "#8a98ac",
        },
        line: "#e2e8f4",
        brand: {
          50: "#eef4ff",
          100: "#dce9ff",
          500: "#245bdb",
          600: "#1b49b4",
          700: "#14367f",
          900: "#122239",
        },
        teal: {
          100: "#d7f6f0",
          400: "#4fcfbd",
          500: "#2fb6a3",
        },
        priority: {
          low: "#2fb6a3",
          medium: "#d9a441",
          high: "#e0843f",
          urgent: "#dd5a5a",
        },
      },
      borderRadius: {
        xl: "14px",
        "2xl": "18px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(23,40,64,0.04), 0 8px 24px rgba(23,40,64,0.06)",
      },
    },
  },
  plugins: [],
};
export default config;
