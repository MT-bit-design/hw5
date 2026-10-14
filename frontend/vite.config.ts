import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// npm run dev -> http://localhost:5173 (fails instead of picking another port).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, open: true },
  preview: { port: 5173, strictPort: true },
});
