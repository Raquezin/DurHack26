import { build } from "esbuild";
import { copyFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const here = (path) => fileURLToPath(new URL(path, import.meta.url));

mkdirSync(here("../static/fonts/"), { recursive: true });
copyFileSync(
  here("node_modules/geist/dist/fonts/geist-sans/Geist-Regular.woff2"),
  here("../static/fonts/Geist-Regular.woff2"),
);

await build({
  entryPoints: [here("src/main.jsx")],
  outfile: here("../static/app.js"),
  bundle: true,
  minify: true,
  format: "iife",
  jsx: "automatic",
  target: "es2020",
  define: { "process.env.NODE_ENV": '"production"' },
  logLevel: "info",
});
