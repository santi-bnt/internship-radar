import { createHash, randomUUID } from "node:crypto";
import type { Browser, BrowserContext, CDPSession, Page } from "playwright";
import { chromium } from "playwright";
import { trustedGreenhouseEmbedUrl } from "../../extension/src/shared/portalNavigation";
import type { AgentFieldResolution, ApplicationAgentPlan, AssistantPageState, ExtensionPayload, PreparedApplicationFile, StoredApplicationSession } from "../../extension/src/shared/types";
import { SessionApi } from "./remote";
import { AgentError, validatePortalUrl } from "./security";
import { createEgressProxy } from "./egress";
import { observeApplicationPage, readOnlyPageState } from "./observer";
import { LocalVisionClient, sanitizedFormHtml, type VisionStatus } from "./vision";
import { evidenceAnswer, localCandidateEvidence, mergeLocalQuestions } from "./local-evidence";

type Active = {
  id: string; connection: StoredApplicationSession; api: SessionApi; payload: ExtensionPayload;
  browser: Browser; context: BrowserContext; page: Page; decisions: AgentFieldResolution[];
  decisionPage: string; files: PreparedApplicationFile[]; world?: { client: CDPSession; contextId: number; page: Page; url: string };
  proxy: Awaited<ReturnType<typeof createEgressProxy>>;
  observationKey?: string; readOnly?: boolean;
  epoch: number; inference?: AbortController;
  localAnalysis?: { key: string; epoch: number; page: Page; viewport: string;
    fields: AssistantPageState["fields"]; decisions: AgentFieldResolution[]; info: NonNullable<AssistantPageState["localVision"]> };
};
export type LocalAction = "scan" | "analyze" | "analyze-local" | "cancel-analysis" | "vision-status" | "fill" | "answer" | "next" | "confirm-submitted" | "close" | "split-screen" | "capture";
export type LocalPageCapture = { imageUrl: string; url: string; title: string; capturedAt: string };

export class LocalBrowserRunner {
  private active?: Active;
  constructor(private readonly browserScript: string, private readonly headless = false, private readonly vision = new LocalVisionClient()) {}

  async start(connection: StoredApplicationSession): Promise<{ id: string }> {
    if (this.active) throw new AgentError("Close the connected local application before starting another one.", 409);
    const api = new SessionApi(connection);
    const payload = await api.json<ExtensionPayload>("");
    if (payload.session.id !== connection.sessionId || payload.resume.id !== payload.session.resume_version_id
      || !payload.ai_settings.owner_user_id || payload.final_submit_policy !== "MANUAL_ONLY") {
      throw new AgentError("Application session ownership or CV identity could not be verified.", 403);
    }
    await validatePortalUrl(payload.session.application_url);
    if (payload.session.application_url !== connection.applicationUrl) throw new AgentError("Application URL does not match the verified session.", 403);
    const proxy = await createEgressProxy();
    let browser: Browser;
    try {
      browser = await chromium.launch({ headless: this.headless,
        proxy: { server: proxy.server, username: proxy.username, password: proxy.password },
        args: ["--proxy-bypass-list=<-loopback>", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
      });
    } catch (error) { await proxy.close(); throw error; }
    try {
      const context = await browser.newContext({ acceptDownloads: false, serviceWorkers: "block", viewport: this.headless ? { width: 1280, height: 720 } : null });
      // Check every request, including redirects and subresources. The browser
      // has no access to the helper, local services, metadata or private hosts.
      await context.route("**/*", async (route) => {
        try { await validatePortalUrl(route.request().url()); await route.continue(); }
        catch { await route.abort("blockedbyclient").catch(() => undefined); }
      });
      await context.routeWebSocket("**/*", (socket) => socket.close());
      const page = await context.newPage();
      const active: Active = {
        id: randomUUID(), connection, api, payload, browser, context, page,
        decisions: [], decisionPage: "", files: [], proxy, epoch: 0,
      };
      this.active = active;
      const watch = (current: Page) => {
        current.on("framenavigated", () => {
          if (active.page === current) { active.epoch += 1; active.inference?.abort(); }
        });
        current.on("close", () => { if (active.page === current) active.inference?.abort(); });
      };
      watch(page);
      context.on("page", (next) => { active.inference?.abort(); active.epoch += 1; active.page = next; active.world = undefined; watch(next); });
      await page.goto(payload.session.application_url, { waitUntil: "domcontentloaded", timeout: 30_000 }).catch((error: Error) => {
        if (!/Timeout/.test(error.name)) throw error;
      });
      return { id: active.id };
    } catch (error) {
      this.active = undefined;
      await browser.close();
      await proxy.close();
      throw error;
    }
  }

  private require(id: string): Active {
    if (!this.active || this.active.id !== id) throw new AgentError("Local application not found. Connect it again.", 404);
    if (Date.parse(this.active.connection.expiresAt) <= Date.now()) throw new AgentError("Application session expired. Close it and reconnect.", 401);
    if (this.active.page.isClosed()) {
      const remaining = this.active.context.pages().filter((page) => !page.isClosed());
      if (!remaining.length) throw new AgentError("The application browser was closed. Close this session and reconnect.", 409);
      this.active.page = remaining[remaining.length - 1];
      this.active.inference?.abort();
      this.active.epoch += 1;
      this.active.world = undefined;
      this.active.decisions = [];
      this.active.decisionPage = "";
    }
    return this.active;
  }

  private async world(active: Active): Promise<{ client: CDPSession; contextId: number }> {
    const currentUrl = active.page.url();
    await validatePortalUrl(currentUrl);
    const origin = new URL(currentUrl).origin;
    if (origin !== new URL(active.connection.applicationUrl).origin && !trustedGreenhouseEmbedUrl(currentUrl)) {
      throw new AgentError("Finish signing in on the browser and return to the original application page before using the assistant.", 409);
    }
    if (active.world?.page === active.page && active.world.url === currentUrl) {
      try {
        await active.world.client.send("Runtime.evaluate", { expression: "1", contextId: active.world.contextId });
        return active.world;
      } catch { active.world = undefined; }
    }
    active.decisions = [];
    active.decisionPage = "";
    const client = await active.context.newCDPSession(active.page);
    const { frameTree } = await client.send("Page.getFrameTree");
    const { executionContextId } = await client.send("Page.createIsolatedWorld", {
      frameId: frameTree.frame.id, worldName: "internship-radar-private",
    });
    active.world = { client, contextId: executionContextId, page: active.page, url: currentUrl };
    await this.evaluate(active, `if (!globalThis.__radarLocal) { ${this.browserScript} }`);
    await this.invoke(active, "connect", [active.payload]);
    await this.invoke(active, "setDecisions", [[]]);
    return active.world;
  }

  private async evaluate<T>(active: Active, expression: string): Promise<T> {
    const world = active.world!;
    const result = await world.client.send("Runtime.evaluate", {
      expression, contextId: world.contextId, awaitPromise: true, returnByValue: true,
    });
    if (result.exceptionDetails) throw new AgentError("The form could not be updated. Refresh its questions or continue manually.", 409);
    return result.result.value as T;
  }

  private async invoke<T>(active: Active, method: string, args: unknown[] = []): Promise<T> {
    return this.evaluate<T>(active, `globalThis.__radarLocal.${method}(...${JSON.stringify(args)})`);
  }

  private async review(active: Active): Promise<AssistantPageState> {
    const observation = await observeApplicationPage(active.page);
    let state: AssistantPageState | undefined;
    let reason = "";
    try {
      await this.world(active);
      state = await this.invoke<AssistantPageState>(active, "review");
    } catch (error) {
      reason = error instanceof AgentError ? error.message : "This portal has no supported form adapter.";
    }
    const readOnly = !state || observation.fields.length > state.fields.length;
    if (readOnly) {
      const assessmentType = state?.assessmentType || observation.assessmentType;
      reason = reason || "El lector detectó campos adicionales en el formulario, iframe o componente. Puedes leer y copiar sugerencias; completa el portal manualmente.";
      state = readOnlyPageState(active.payload, observation, reason);
      state.assessmentType = assessmentType;
    }
    state = state!;
    const documentKey = createHash("sha256").update(JSON.stringify([observation.url, readOnly,
      state.fields.map((field) => [field.fieldId, field.label, field.availableOptions])])).digest("hex");
    if (active.observationKey && active.observationKey !== documentKey) {
      active.decisions = [];
      active.decisionPage = "";
      if (!readOnly) await this.invoke(active, "setDecisions", [[]]);
    }
    active.observationKey = documentKey;
    active.readOnly = readOnly;
    state.agentDecisions = active.decisions.filter((decision) => state!.fields.some((field) => field.fieldId === decision.field_id));
    state.pageObservation = { url: observation.url, title: observation.title, readAt: new Date().toISOString(),
      framesScanned: observation.framesScanned, unreadableFrames: observation.unreadableFrames,
      readOnly, reason, documentKey };
    if (!state.fields.length) state.lastActionMessage = "No se encontraron preguntas editables. Abre el formulario de aplicación en el navegador local, termina el inicio de sesión y vuelve a leer. Usa la captura para comprobar qué página está abierta.";
    const local = active.localAnalysis;
    if (local) {
      if (local.key === documentKey && local.epoch === active.epoch && local.page === active.page && local.viewport === await this.viewportKey(active.page)) {
        state.fields = local.fields;
        state.agentDecisions = local.decisions;
        state.localVision = local.info;
        state.pageObservation.readOnly = true;
        state.pageObservation.reason = "Lectura combinada local. Revisa y copia las sugerencias.";
        state.lastActionMessage = local.info.message;
        active.readOnly = true;
      } else {
        active.localAnalysis = undefined;
        active.decisions = [];
        active.decisionPage = "";
        state.agentDecisions = [];
      }
    }
    return state;
  }

  private async viewportKey(page: Page): Promise<string> {
    return page.evaluate(() => JSON.stringify([scrollX, scrollY, innerWidth, innerHeight]));
  }

  private async analyzeLocal(active: Active): Promise<AssistantPageState> {
    active.localAnalysis = undefined;
    active.decisions = [];
    active.decisionPage = "";
    const state = await this.review(active);
    if (state.assessmentType || state.isReviewPage) throw new AgentError("Esta sección requiere tu revisión manual; no se analizarán evaluaciones ni el envío final.", 409);
    const page = active.page, epoch = active.epoch, key = active.observationKey!, viewport = await this.viewportKey(page);
    const controller = new AbortController();
    active.inference = controller;
    const remaining = Date.parse(active.connection.expiresAt) - Date.now();
    if (remaining <= 0) throw new AgentError("La sesión expiró. Vuelve a conectarla.", 401);
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(Math.min(180000, remaining))]);
    try {
      // Masks filled controls, including shadow DOM and frame controls. The image
      // goes directly to loopback Ollama, never to SessionApi or a cloud model.
      const masks = page.frames().map((frame) => frame.locator("input:not([type='button']):not([type='submit']), textarea, select, [contenteditable='true'], [role='textbox']"));
      const image = await page.screenshot({ type: "jpeg", quality: 80, scale: "css", fullPage: false, mask: masks, timeout: 8000 });
      const evidence = localCandidateEvidence(active.payload);
      const result = await this.vision.interpret({ image: image.toString("base64"), html: sanitizedFormHtml(state.fields),
        fields: state.fields.slice(0, 80).map((field) => ({ id: field.fieldId, label: field.label })), evidence,
        target: { company: active.payload.session.company, title: active.payload.resume.target_role,
          requirements: String(active.payload.session.job_snapshot_json.requirements || active.payload.session.job_snapshot_json.description || "").slice(0, 4000) } }, signal);
      if (this.require(active.id) !== active || controller.signal.aborted || active.page !== page || active.epoch !== epoch) {
        throw new AgentError("La página o la sesión cambiaron durante la lectura. Vuelve a leerla.", 409);
      }
      await this.review(active);
      if (active.observationKey !== key || viewport !== await this.viewportKey(page)) throw new AgentError("El formulario o la captura cambiaron. Vuelve a leer la página.", 409);
      if (result.screen_state !== "APPLICATION") throw new AgentError(result.screen_state === "LOGIN"
        ? "Termina el inicio de sesión y abre el formulario de aplicación antes de analizarlo."
        : "El modelo no confirmó un formulario editable. Revisa el portal personalmente y vuelve a leer cuando estés en las preguntas.", 409);
      const merged = mergeLocalQuestions(state.fields, result.questions, key);
      const decisions = merged.mapped.map(({ question, fieldId }) => evidenceAnswer(question, fieldId, evidence, this.vision.config.model));
      active.localAnalysis = { key, epoch, page, viewport, fields: merged.fields, decisions,
        info: { model: this.vision.config.model, engine: "LOCAL_HTML_VISION", analyzedAt: new Date().toISOString(), domFields: state.fields.length,
          imageQuestions: merged.fields.length - state.fields.length,
          message: `HTML y captura analizados en este equipo. ${decisions.length} preguntas interpretadas; las respuestas usan evidencia del perfil/CV y requieren tu revisión.` } };
      active.decisions = decisions;
      active.decisionPage = page.url();
      return this.review(active);
    } finally { if (active.inference === controller) active.inference = undefined; }
  }

  private async analyze(active: Active): Promise<AssistantPageState> {
    const state = await this.review(active);
    if (state.isReviewPage || state.assessmentType) throw new AgentError("This section needs your manual review.", 409);
    if (!state.fields.length) throw new AgentError(state.lastActionMessage, 409);
    const pageUrl = active.page.url();
    const documentKey = active.observationKey;
    const analysisUrl = new URL(pageUrl);
    analysisUrl.search = "";
    analysisUrl.hash = "";
    const plan = await active.api.json<ApplicationAgentPlan>("/agent/analyze", {
      page_url: analysisUrl.href.slice(0, 3000), page_title: (await active.page.title()).slice(0, 500),
      fields: state.fields.slice(0, 250).map((field) => ({
        field_id: field.fieldId, raw_label: field.label.slice(0, 2000), nearby_text: field.nearbyText.slice(0, 4000),
        control_type: field.controlType, available_options: field.availableOptions,
        required: field.required, maxlength: field.maxlength ? Math.min(field.maxlength, 10000) : undefined,
        // Existing answers are kept on the computer; analysis needs labels,
        // not the contents of password, legal or personal form fields.
      })),
    });
    if (active.page.url() !== pageUrl) throw new AgentError("The page changed while reading questions. Read them again.", 409);
    await this.review(active);
    if (active.observationKey !== documentKey) throw new AgentError("The form changed while reading questions. Read them again.", 409);
    active.decisions = plan.resolutions;
    active.decisionPage = pageUrl;
    if (!active.readOnly) await this.invoke(active, "setDecisions", [active.decisions]);
    return this.review(active);
  }

  private async attachResume(active: Active, file: PreparedApplicationFile): Promise<boolean> {
    const resumeLabel = /resume|curriculum|curriculum vitae|\bcv\b/i;
    const unrelatedLabel = /portfolio|cover letter|supporting documents|project materials/i;
    for (const frame of active.page.frames()) {
      const inputs = await frame.locator("input[type='file']").all().catch(() => []);
      for (const input of inputs) {
        const metadata = await input.evaluate((element) => {
          const input = element as HTMLInputElement;
          const labels = [...(input.labels || [])].map((label) => label.innerText || label.textContent || "");
          const labelledBy = (input.getAttribute("aria-labelledby") || "").split(/\s+/)
            .map((id) => document.getElementById(id)?.textContent || "");
          const parentText = input.parentElement?.innerText || "";
          return [input.id, input.name, input.getAttribute("aria-label"), ...labels, ...labelledBy, parentText.slice(0, 500)]
            .filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
        }).catch(() => "");
        if (!resumeLabel.test(metadata) || unrelatedLabel.test(metadata)) continue;
        try {
          const alreadyAttached = await input.evaluate((element, filename) =>
            (element as HTMLInputElement).files?.[0]?.name === filename, file.filename);
          if (!alreadyAttached) await input.setInputFiles({
            name: file.filename, mimeType: file.mimeType, buffer: Buffer.from(file.base64, "base64"),
          });
          return await input.evaluate((element, filename) =>
            (element as HTMLInputElement).files?.[0]?.name === filename, file.filename);
        } catch {
          // Keep looking for a supported resume input; never upload to an
          // unlabeled or unrelated file field.
        }
      }
    }
    return false;
  }

  async action(id: string, action: LocalAction, body: Record<string, unknown> = {}): Promise<AssistantPageState | LocalPageCapture | VisionStatus | { closed: true } | { arranged: true } | { cancelled: true }> {
    if (action === "close") { if (this.active?.id !== id) throw new AgentError("Local application not found.", 404); await this.close(); return { closed: true }; }
    const active = this.require(id);
    if (action === "cancel-analysis") { active.inference?.abort(); return { cancelled: true }; }
    if (action === "vision-status") return this.vision.status();
    if (action === "analyze-local") return this.analyzeLocal(active);
    if (action === "capture") {
      const url = active.page.url();
      await validatePortalUrl(url);
      const title = await active.page.title();
      const masks = active.page.frames().map((frame) => frame.locator("input[type='password'], input[autocomplete*='password'], input[autocomplete='one-time-code'], input[name*='otp' i], input[id*='otp' i]"));
      const image = await active.page.screenshot({ type: "jpeg", quality: 65, fullPage: false, scale: "css", mask: masks, timeout: 8000 });
      if (active.page.url() !== url) throw new AgentError("The page changed during capture. Capture it again.", 409);
      return { imageUrl: `data:image/jpeg;base64,${image.toString("base64")}`, url,
        title, capturedAt: new Date().toISOString() };
    }
    if (action === "split-screen") {
      const { left, top, width, height } = body;
      if (![left, top, width, height].every((value) => typeof value === "number" && Number.isSafeInteger(value))
        || Math.abs(Number(left)) > 32768 || Math.abs(Number(top)) > 32768
        || Number(width) < 320 || Number(width) > 16384 || Number(height) < 320 || Number(height) > 16384) {
        throw new AgentError("Invalid split-screen window dimensions.");
      }
      const client = await active.context.newCDPSession(active.page);
      try {
        const { windowId } = await client.send("Browser.getWindowForTarget");
        await client.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal" } });
        await client.send("Browser.setWindowBounds", { windowId, bounds: { left: Number(left), top: Number(top), width: Number(width), height: Number(height) } });
      } finally { await client.detach(); }
      return { arranged: true };
    }
    if (action === "scan") return this.review(active);
    if (action === "analyze") return this.analyze(active);
    if (action === "fill") {
      const state = await this.analyze(active);
      if (active.readOnly) throw new AgentError("Solo lectura en este portal. Revisa y copia las respuestas sugeridas; sube el CV y completa los campos manualmente.", 409);
      if (!active.files.length) {
        active.files = [{ kind: "RESUME", filename: active.payload.session.resume_filename.replace(/[\\/:*?"<>|]/g, "_"),
          mimeType: "application/pdf", base64: Buffer.from(await active.api.resume()).toString("base64"), versionId: active.payload.resume.id }];
      }
      const resume = active.files.find((file) => file.kind === "RESUME");
      const resumeField = state.fields.some((field) => field.controlType === "file"
        && (field.label === "Resume / CV" || /resume|curriculum|\bcv\b/i.test(`${field.label} ${field.fieldId}`)));
      if (resume && resumeField && !(await this.attachResume(active, resume))) {
        throw new AgentError("I filled the profile, but the CV could not be attached. Use the application's resume upload control manually, then select Refresh form.", 409);
      }
      await this.invoke(active, "fill", [active.files]);
    } else if (action === "answer") {
      await this.review(active);
      if (active.readOnly) throw new AgentError("Copia esta respuesta al portal manualmente: este formulario está en modo de lectura.", 409);
      if (active.decisionPage !== active.page.url() || typeof body.fieldId !== "string" || typeof body.answer !== "string" || body.answer.length > 10_000) {
        throw new AgentError("Read the questions on this page again before using an answer.", 409);
      }
      if (!(await this.invoke<boolean>(active, "answer", [body.fieldId, body.answer]))) throw new AgentError("Copy this answer to the application manually.", 409);
    } else if (action === "confirm-submitted") {
      const state = await this.review(active);
      if (!state.isConfirmationPage) throw new AgentError("Submit manually in the browser and verify its confirmation page first.", 409);
      await active.api.json("/confirm-submitted", { confirmation_text: state.confirmationText, confirmation_url: active.page.url() });
    } else if (action === "next") {
      const state = await this.review(active);
      if (active.readOnly) throw new AgentError("Avanza directamente en el portal y vuelve a leer las preguntas.", 409);
      const missing = state.fields.some((field) => field.required && !field.currentValue && field.controlType !== "file");
      if (missing || state.pendingQuestions.length || state.isReviewPage || state.assessmentType) throw new AgentError("Review the remaining required fields in the browser before continuing.", 409);
      if (!(await this.invoke<boolean>(active, "next"))) throw new AgentError("Continue on the browser. Final submission stays manual.", 409);
      await active.page.waitForTimeout(500);
    } else throw new AgentError("Unsupported local action.");
    return this.review(active);
  }

  async close(): Promise<void> {
    const active = this.active;
    this.active = undefined;
    active?.inference?.abort();
    try { await active?.browser.close(); } finally { await active?.proxy.close(); }
  }

  async expire(): Promise<void> {
    if (this.active && Date.parse(this.active.connection.expiresAt) <= Date.now()) await this.close();
  }
}
