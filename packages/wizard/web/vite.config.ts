import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

// The build lands inside the Python package rather than beside this source, so that
// `uv run metis wizard serve` works on a machine with no JavaScript toolchain. The output
// is committed for the same reason.
const STATIC_DIR = fileURLToPath(
  new URL("../src/metis/wizard/adapters/web/static", import.meta.url),
);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: STATIC_DIR,
    emptyOutDir: true,
  },
  server: {
    // `npm run dev` talks to a `metis wizard serve` running beside it.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
