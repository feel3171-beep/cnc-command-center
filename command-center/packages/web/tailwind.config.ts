import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "#0d0d0d",
          secondary: "#171717",
          tertiary: "#1e1e1e",
          hover: "#262626",
          active: "#2a2a2a",
        },
        border: {
          primary: "#2a2a2a",
          secondary: "#333333",
        },
        text: {
          primary: "#e5e5e5",
          secondary: "#a3a3a3",
          muted: "#737373",
        },
        accent: {
          green: "#22c55e",
          orange: "#f97316",
          red: "#ef4444",
          blue: "#3b82f6",
          purple: "#8b5cf6",
          yellow: "#eab308",
        },
        priority: {
          p0: "#ef4444",
          p1: "#f97316",
          p2: "#3b82f6",
          p3: "#6b7280",
        },
      },
      fontFamily: {
        sans: ["Pretendard", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
