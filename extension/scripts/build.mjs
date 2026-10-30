import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, "dist");
await rm(dist, { recursive: true, force: true });
await mkdir(resolve(dist, "sidepanel"), { recursive: true });

await build({
  absWorkingDir: root,
  entryPoints: {
    background: resolve(root, "src/background/index.ts"),
    "web-bridge": resolve(root, "src/content/webBridge.ts"),
    assistant: resolve(root, "src/content/assistant.ts"),
    "sidepanel/index": resolve(root, "src/sidepanel/index.ts")
  },
  outdir: dist,
  bundle: true,
  format: "esm",
  target: "chrome120",
  sourcemap: false,
  minify: true,
  legalComments: "none"
});

await Promise.all([
  cp(resolve(root, "manifest.json"), resolve(dist, "manifest.json")),
  cp(resolve(root, "src/sidepanel/index.html"), resolve(dist, "sidepanel/index.html")),
  cp(resolve(root, "src/sidepanel/styles.css"), resolve(dist, "sidepanel/styles.css"))
]);
