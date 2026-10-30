import { build } from "esbuild";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
await mkdir(new URL("../dist/", import.meta.url), { recursive: true });
await build({ absWorkingDir: root, entryPoints: ["src/browser.ts"], bundle: true, format: "iife", platform: "browser", target: "chrome120", outfile: "dist/browser.js" });
await build({ absWorkingDir: root, entryPoints: ["src/server.ts"], bundle: true, format: "esm", platform: "node", packages: "external", target: "node22", outfile: "dist/server.js" });
