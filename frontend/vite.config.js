import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// El dev server corre en 5173 (origen permitido por el CORS del backend).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
