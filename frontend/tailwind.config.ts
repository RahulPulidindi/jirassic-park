import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Atlassian / Jira palette. The blue is the canonical "create" blue;
        // the ink ramp mirrors Atlassian's neutral N0..N900 scale.
        brand: {
          50: "#deebff",   // active item bg
          100: "#b3d4ff",
          500: "#0052cc",  // primary action (Create button, links)
          600: "#0747a6",  // hover
          700: "#053078",
        },
        ink: {
          900: "#091e42",  // primary text
          800: "#172b4d",
          700: "#253858",  // sidebar/header text
          600: "#42526e",
          500: "#6b778c",  // secondary text
          400: "#8993a4",  // muted/icons
          300: "#a5adba",
          200: "#dfe1e6",  // borders
          100: "#ebecf0",  // hover bg
          50: "#f4f5f7",   // canvas bg
        },
        status: {
          todo: "#42526e",
          inprogress: "#0052cc",
          inreview: "#ff8b00",
          done: "#00875a",
        },
        priority: {
          highest: "#de350b",
          high: "#ff5630",
          medium: "#ffab00",
          low: "#0065ff",
          lowest: "#5e6c84",
        },
        issuetype: {
          story: "#00875a",
          task: "#0052cc",
          bug: "#de350b",
          epic: "#6554c0",
          subtask: "#0065ff",
        },
      },
      fontFamily: {
        sans: [
          "InterVariable",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "Courier New",
          "monospace",
        ],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgba(11, 18, 38, 0.05), 0 1px 3px 0 rgba(11, 18, 38, 0.07)",
        pop: "0 4px 16px -2px rgba(11, 18, 38, 0.12), 0 2px 6px -1px rgba(11, 18, 38, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
