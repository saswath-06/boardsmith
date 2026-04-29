import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  preview: {
    // Railway assigns hostnames like *.up.railway.app and may also use
    // a custom domain. Accept anything in production; local dev still
    // works without setting this.
    allowedHosts: true,
  },
});
