import { readFileSync, readdirSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const extensionRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return [".ts", ".html", ".json"].includes(extname(path)) ? [path] : [];
  });
}

describe("extension security boundary", () => {
  it("contains no embedded API keys or private key material", () => {
    const bundleInput = sourceFiles(join(extensionRoot, "src"))
      .map((path) => readFileSync(path, "utf8"))
      .join("\n");
    expect(bundleInput).not.toMatch(/\bsk-[A-Za-z0-9_-]{20,}\b/);
    expect(bundleInput).not.toMatch(/\bAIza[A-Za-z0-9_-]{20,}\b/);
    expect(bundleInput).not.toContain("BEGIN PRIVATE KEY");
  });

  it("keeps broad career-site access optional and static access limited to Internship Radar", () => {
    const manifest = JSON.parse(readFileSync(join(extensionRoot, "manifest.json"), "utf8")) as {
      host_permissions: string[];
      optional_host_permissions: string[];
    };
    expect(manifest.host_permissions).not.toContain("https://*/*");
    expect(manifest.optional_host_permissions).toContain("https://*/*");
    expect(manifest.host_permissions.every((origin) => origin.includes("internship-radar") || origin.includes("intership-radar") || origin.includes("localhost"))).toBe(true);
  });

  it("requests optional portal access directly from the user click handler", () => {
    const sidepanel = readFileSync(join(extensionRoot, "src", "sidepanel", "index.ts"), "utf8");
    const background = readFileSync(join(extensionRoot, "src", "background", "index.ts"), "utf8");

    expect(sidepanel).toContain("chrome.permissions.request({ origins })");
    expect(background).not.toContain("chrome.permissions.request(");
    expect(background).toContain("chrome.permissions.contains({ origins: [origin] })");
  });
});
