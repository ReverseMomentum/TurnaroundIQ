import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./", // Capacitor serves from the app bundle
  build: { chunkSizeWarningLimit: 1000 }, // single-page app; charts library is large
});
