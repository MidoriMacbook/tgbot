import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: {
    outDir: "../app/web/static/web/dist", emptyOutDir: true,
    rollupOptions: { input: "src/main.tsx", output: { entryFileNames: "panel.js", assetFileNames: "panel.[ext]" } },
  },
});
