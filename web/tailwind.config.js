/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Scientific light theme (Req 14.4). Navy + teal accents on
        // white/off-white; orange/red reserved for active alerts only.
        navy: {
          DEFAULT: "#0f2742",
          600: "#1b3a5b",
          900: "#0f2742",
        },
        teal: {
          DEFAULT: "#0f9b8e",
          500: "#14b8a6",
          600: "#0f9b8e",
        },
        surface: {
          DEFAULT: "#ffffff",
          muted: "#f8fafc",
        },
        alert: {
          // Restrained alert colors — not for decorative use.
          warn: "#f59e0b",
          danger: "#dc2626",
        },
      },
    },
  },
  plugins: [],
};
