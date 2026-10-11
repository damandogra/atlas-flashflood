import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages serves the site under /<repo>/ ; override with BASE_PATH for other hosts.
export default defineConfig({
  base: process.env.BASE_PATH ?? "/atlas-flashflood/",
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: { manualChunks: { maplibre: ["maplibre-gl"], charts: ["recharts"], supabase: ["@supabase/supabase-js"] } },
    },
  },
});
