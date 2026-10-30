import { readFile } from "node:fs/promises";
import { createAgentServer } from "./http";
import { LocalBrowserRunner } from "./runner";
import { PORT } from "./security";

const script = await readFile(new URL("./browser.js", import.meta.url), "utf8");
const runner = new LocalBrowserRunner(script);
const { server, key } = createAgentServer(runner);
server.listen(PORT, "127.0.0.1", () => {
  console.log(`Internship Radar local assistant is ready on 127.0.0.1:${PORT}.`);
  console.log(`Connection code: ${key}`);
  console.log("Keep this terminal open. Paste the code into Apply with Assistant > Local browser.");
  console.log("HTML + screenshot inference uses local Ollama only (default: gemma3:4b on 127.0.0.1:11434). No cloud model fallback.");
});
server.on("error", () => { console.error("Could not start the local assistant. Port 43123 may already be in use."); process.exitCode = 1; });
const expiry = setInterval(() => { void runner.expire().catch(() => undefined); }, 30_000);
expiry.unref();
for (const signal of ["SIGINT", "SIGTERM"] as const) process.on(signal, () => {
  clearInterval(expiry); server.close(); void runner.close().finally(() => process.exit(0));
});
