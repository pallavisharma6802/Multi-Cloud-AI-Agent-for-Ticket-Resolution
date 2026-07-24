import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        priority: {
          low: "#4ade80",
          medium: "#facc15",
          high: "#fb923c",
          urgent: "#f87171",
        },
      },
    },
  },
  plugins: [],
};
export default config;
