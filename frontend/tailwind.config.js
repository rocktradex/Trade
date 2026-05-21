/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        red: {
          550: "#CC0000",
          600: "#B80000",
        },
      },
    },
  },
  plugins: [],
};
