import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // the waitlist API (server/waitlist_api.py) runs separately on 8090 in development
    proxy: { "/api": "http://127.0.0.1:8090" },
  },
});
