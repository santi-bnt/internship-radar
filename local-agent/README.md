# Local application assistant

This desktop helper runs a visible Chromium browser without installing an extension. It reuses Internship Radar's scoped application session and selected CV. Its **HTML + image** reader runs on your own device using Ollama and a downloaded vision model. No API key or cloud-model fallback is used for this reader. The hosted application continues to store your profile and generate CVs through the existing pipeline.

## One-click local vision on Windows

Double-click `start-local-assistant.cmd` at the repository root. It starts Docker Desktop if needed, launches the official Ollama `0.40.11` container bound only to `127.0.0.1:11434`, downloads `gemma3:4b` if missing, and starts the native helper/browser. First setup needs internet and several GB of disk space; later starts reuse the named model volume. NVIDIA GPU support is selected when `nvidia-smi` is available; otherwise CPU inference is supported but slower.

Docker hosts the model only. The visible browser stays on Windows so you can sign in, choose files and review the actual employer page. This is a launcher, not an Electron installer. Node.js 22+ and Docker Desktop are prerequisites.

Equivalent command:

```powershell
.\start-local-assistant.ps1 -WithDockerVision
```

Native Ollama is also supported: download `gemma3:4b` with `ollama pull gemma3:4b`, disable Ollama cloud features (`OLLAMA_NO_CLOUD=1`), then use the original launcher without `-WithDockerVision`. Optional trusted process settings are `RADAR_LOCAL_AI_URL=http://127.0.0.1:11434` and `RADAR_LOCAL_VISION_MODEL=gemma3:4b`. Remote endpoints, cloud model names and aliases reporting remote hosting are rejected; the model must advertise vision capability.

## Start on Windows

From the repository root, run:

```powershell
.\start-local-assistant.ps1
```

Node.js 22 or later is required. First startup installs the locked npm dependencies and Playwright's Chromium. Subsequent startups reuse those installations. Keep the terminal open and copy its **Connection code**. The code changes whenever the helper restarts and is never saved in the repository.

Alternatively, inside `local-agent`, run `npm ci`, `npm run install-browser`, `npm run build`, and `npm start`.

## Apply

1. Open a job and choose **Apply with Assistant**. If a compiled CV exists for the job, choose to reuse it or regenerate it. Otherwise the normal queue generates and validates one.
2. Select **Local browser — no extension**, paste the connection code and connect. Allow local network access if the browser asks. Supported web origins are the two production Vercel domains and localhost/127.0.0.1 port 3000.
3. Start the application. The helper verifies the scoped backend session and opens its official application URL.
4. Sign in manually in the separate browser, then use **Leer HTML + imagen (local)**. The helper sends a masked viewport screenshot and an allowlisted HTML outline of labels/options directly to local Ollama. It merges DOM questions and image-only questions, then builds suggested answers from the session's verified facts and selected CV evidence. Review/copy answers and upload the CV directly in the employer portal.
5. Review each section and submit manually in the browser. After a confirmation page appears, **Confirm Applied** records the submission through the existing application-tracking endpoint.
6. Close the local browser from the controls when finished. If you navigated away and lost the controls, use **Close any previous local browser** before starting another application, or restart the helper.

Use **Pantalla dividida** to arrange the employer browser and assistant beside each other. **Comprobar visión local** checks the installed model. **Ver captura de la página** is a separate preview. Combined local inference uses its own screenshot with form controls masked; raw page HTML, scripts, tokens and saved field values are not sent to the model. Images and prompts stay in memory and are never sent through the hosted backend or an external AI provider. Masking reduces incidental disclosure but is not a guarantee that every piece of personal text rendered by the portal is hidden from the local model.

The model identifies questions and selects existing evidence IDs; it does not author accomplishments or legal answers. Project answers use validated bullets from the bound resume; missing evidence remains manual. Academic/personal projects are not treated as employment. Visa, authorization, consent, salary and other sensitive questions require personal confirmation. Vision suggestions are read-only and never click, type, navigate or submit. A page/session/viewport change invalidates the result. **Cancelar lectura** aborts inference without closing the application. Missing/failed local vision reports an error instead of falling back to cloud inference. Existing adapter endpoints remain for compatibility; the new sidebar uses the local reader.

The reader inspects the helper's browser, not unrelated Chrome tabs. It reports the current title, URL, scanned documents, field count and read time. It can read visible public iframes, open Shadow DOM and fields outside HTML form tags. Unknown adapters or public ATS redirects can use a read-only fallback: review/copy suggestions and upload files manually. Write actions retain the existing supported-adapter and origin checks. Closing a sign-in popup returns reading to the remaining browser page. Login, MFA, CAPTCHA, assessments and final submission stay manual. Live sites have not been used for submitting test applications.

## Isolation and security

- HTTP control binds only to `127.0.0.1:43123`. Every request requires an exact trusted web origin, matching loopback Host header and a random bearer connection code. CORS private-network preflights are supported. Unknown commands and oversized request bodies are rejected; operations run sequentially.
- Backend requests use only the short-lived application-session token. The API origin must match the connected web app. The payload's session ID and CV ID must match before launching. Tokens and CV bytes stay in memory; no personal browser profile, cookies, passwords, account keys or screenshots are saved.
- Each application has a fresh browser context. Profile data and adapter code run in a Chromium isolated world, not the employer's JavaScript world. The employer sees the fields you fill, not the full profile snapshot or backend token.
- Every browser request, redirect and subresource is checked against public HTTPS and public DNS addresses. An authenticated loopback HTTPS tunnel proxy connects to the exact approved numeric IP, preventing a second DNS lookup from rebinding the request to a private address. TLS stays end-to-end with the employer; no passwords or form contents are decrypted by the proxy. Private/loopback/reserved addresses, alternate ports and non-HTTPS requests are blocked. Chromium's loopback proxy bypass and non-proxied WebRTC UDP are disabled. WebSockets and service workers are disabled in this initial version.
- Sessions expire with their backend token. **Close local browser** or Ctrl+C ends the helper/browser; no application is marked Applied automatically.

## Validation

`npm run typecheck`, `npm run build`, `npm test`. Targeted tests cover loopback-only inference, cloud aliases, malformed/oversized output, unknown evidence IDs, candidate isolation, no image/HTML sent to SessionApi, DOM+image merging, cancellation, stale navigation/viewport results and existing browser safety. Tests make no real job applications. Real vision is an explicit opt-in test: set `RADAR_LIVE_VISION_TEST=1` and run `npm test -- tests/vision-live.test.ts`; it uses a synthetic page and fake candidate facts.

Stop the model service without deleting downloaded weights:

```powershell
docker compose --project-name radar-local-ai -f local-agent/compose.vision.yml stop
```

Docker settings follow the official [Ollama Docker guide](https://docs.ollama.com/docker), [vision API](https://docs.ollama.com/capabilities/vision), [structured output API](https://docs.ollama.com/capabilities/structured-outputs), and [local-only cloud-disable setting](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features). Model: [gemma3:4b](https://ollama.com/library/gemma3:4b).

The browser-context and isolated-world implementation uses the official [Playwright browser context API](https://playwright.dev/docs/api/class-browsercontext) and [CDP session API](https://playwright.dev/docs/api/class-cdpsession).
