import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-ibm-plex-sans)", "IBM Plex Sans", "system-ui", "sans-serif"],
        title: ["var(--font-libre-franklin)", "Libre Franklin", "sans-serif"],
        mono: ["var(--font-ibm-plex-mono)", "IBM Plex Mono", "monospace"],
      },
      colors: {
        background: "#FAF6EE",
        foreground: "#221F1A",
        card: "#FFFFFF",
        border: "#E7DECF",
        divider: "#EFE8DB",
        primary: {
          DEFAULT: "#2F6B4F",
          hover: "#3E8E63",
          foreground: "#FFFFFF",
        },
        accent: {
          DEFAULT: "#E2A33C",
          hover: "#C2802B",
          foreground: "#3A2A0E",
        },
        terracotta: "#C25E3E",
        info: "#3A7CA5",
        muted: {
          DEFAULT: "#9A9080",
          foreground: "#6B6357",
          light: "#C3BAA8",
        },
        ai: {
          bg: "#EEF5F0",
          border: "#CDE3D6",
        },
        stage: "#1A1E1A",
        success: {
          DEFAULT: "#2F8F4E",
          dot: "#5FD08A",
        },
        warning: "#E2A33C",
        error: "#C2503A",
      },
      borderRadius: {
        btn: "10px",
        chip: "11px",
        card: "14px",
        "card-lg": "16px",
        thumb: "9px",
        logo: "9px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(34,31,26,0.04), 0 6px 20px rgba(34,31,26,0.05)",
        stage:
          "0 1px 2px rgba(34,31,26,0.06), 0 10px 30px rgba(34,31,26,0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
