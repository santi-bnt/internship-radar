import { extensionApi } from "../api/client";
import type { RuntimeMessage } from "../shared/messages";
import { trustedGreenhouseEmbedUrl } from "../shared/portalNavigation";
import type { StoredApplicationSession } from "../shared/types";
import { analyzeVisibleApplicationLocally } from "./localVision";

const STORAGE_KEY = "activeApplicationSession";
const optionalSidePanel = (chrome as unknown as { sidePanel?: Partial<typeof chrome.sidePanel> }).sidePanel;
const allowedWebOrigins = new Set([
  "https://your-app.vercel.app",
  "https://your-app.vercel.app",
  "http://localhost:3000"
]);

async function getSession(): Promise<StoredApplicationSession | null> {
  const result = await chrome.storage.session.get(STORAGE_KEY);
  const session = result[STORAGE_KEY] as StoredApplicationSession | undefined;
  if (!session) return null;
  if (Date.parse(session.expiresAt) <= Date.now()) {
    await chrome.storage.session.remove(STORAGE_KEY);
    return null;
  }
  return session;
}

async function requireSession(): Promise<StoredApplicationSession> {
  const session = await getSession();
  if (!session) throw new Error("No active Application Session. Start one from Internship Radar.");
  return session;
}

function senderOrigin(sender: chrome.runtime.MessageSender): string {
  try { return new URL(sender.url || "").origin; } catch { return ""; }
}

function bytesToBase64(bytes: ArrayBuffer): string {
  const view = new Uint8Array(bytes);
  let binary = "";
  for (let offset = 0; offset < view.length; offset += 0x8000) {
    binary += String.fromCharCode(...view.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

function filenameFromDisposition(disposition: string): string {
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return (match?.[1] || "Internship_Radar_Recommended_Resume.pdf").replace(/[\\/:*?"<>|]/g, "_");
}

function portalOriginPattern(urlValue: string): string {
  const url = new URL(urlValue);
  if (url.protocol !== "https:") throw new Error("Apply Assistant only activates on secure HTTPS career portals.");
  return `${url.origin}/*`;
}

function hasNativeSidePanel(): boolean {
  return Boolean(optionalSidePanel?.setOptions && optionalSidePanel?.setPanelBehavior);
}

async function configureAssistantPanel(tabId: number): Promise<void> {
  if (!optionalSidePanel?.setOptions) return;
  await optionalSidePanel.setOptions({ tabId, enabled: true, path: "sidepanel/index.html" });
}

async function injectAssistant(tabId: number): Promise<void> {
  await chrome.scripting.executeScript({ target: { tabId }, files: ["assistant.js"] });
  await configureAssistantPanel(tabId);
  await chrome.tabs.sendMessage(tabId, { type: "APPLICATION_SESSION_AVAILABLE" }).catch(() => undefined);
}

async function waitForTabComplete(tabId: number, timeoutMs = 15_000): Promise<void> {
  const current = await chrome.tabs.get(tabId);
  if (current.status === "complete") return;
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("The Greenhouse application did not finish loading."));
    }, timeoutMs);
    const listener = (updatedTabId: number, changeInfo: chrome.tabs.TabChangeInfo) => {
      if (updatedTabId !== tabId || changeInfo.status !== "complete") return;
      clearTimeout(timeout);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    };
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function openTrustedEmbeddedApplication(tabId: number): Promise<string | null> {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const frame = [...document.querySelectorAll<HTMLIFrameElement>("iframe[src]")]
        .find((item) => item.title === "Greenhouse Job Application" || item.src.includes("greenhouse.io/embed/job_app"));
      return frame?.src || null;
    }
  });
  const embeddedUrl = trustedGreenhouseEmbedUrl(results[0]?.result);
  if (!embeddedUrl) return null;
  const embeddedOrigin = portalOriginPattern(embeddedUrl);
  if (!(await chrome.permissions.contains({ origins: [embeddedOrigin] }))) {
    throw new Error("Greenhouse form access was not granted. Enable this career portal again.");
  }
  await chrome.tabs.update(tabId, { url: embeddedUrl });
  await waitForTabComplete(tabId);
  return embeddedUrl;
}

chrome.runtime.onInstalled.addListener(() => {
  if (optionalSidePanel?.setPanelBehavior) {
    void optionalSidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  }
});

if (!hasNativeSidePanel()) {
  chrome.action.onClicked.addListener((tab) => {
    const query = tab.id ? `?tabId=${tab.id}` : "";
    void chrome.tabs.create({ url: chrome.runtime.getURL(`sidepanel/index.html${query}`) });
  });
}

chrome.runtime.onMessage.addListener((message: RuntimeMessage, sender, sendResponse) => {
  void (async () => {
    try {
      switch (message.type) {
        case "PING": {
          if (!allowedWebOrigins.has(senderOrigin(sender))) throw new Error("Extension probe came from an untrusted origin.");
          sendResponse({ ok: true, data: { version: chrome.runtime.getManifest().version, presentation: hasNativeSidePanel() ? "side_panel" : "tab" } });
          break;
        }
        case "CONNECT_APPLICATION_SESSION": {
          if (!allowedWebOrigins.has(senderOrigin(sender))) throw new Error("Connection request came from an untrusted origin.");
          const apiOrigin = new URL(message.payload.apiBaseUrl).origin;
          if (apiOrigin !== senderOrigin(sender)) throw new Error("Application Session API origin mismatch.");
          const session: StoredApplicationSession = { ...message.payload };
          if (!session.token || session.token.length < 40 || Date.parse(session.expiresAt) <= Date.now()) throw new Error("Invalid or expired Application Session token.");
          await chrome.storage.session.set({ [STORAGE_KEY]: session });
          if (sender.tab?.id) await configureAssistantPanel(sender.tab.id);
          sendResponse({ ok: true, data: { presentation: hasNativeSidePanel() ? "side_panel" : "tab" } });
          break;
        }
        case "GET_ACTIVE_SESSION": sendResponse({ ok: true, data: await getSession() }); break;
        case "GET_APPLICATION_PAYLOAD": sendResponse({ ok: true, data: await extensionApi.payload(await requireSession()) }); break;
        case "ANALYZE_APPLICATION_PAGE": sendResponse({ ok: true, data: await extensionApi.analyzePage(await requireSession(), message.payload) }); break;
        case "APPROVE_AGENT_MAPPING": sendResponse({ ok: true, data: await extensionApi.approveMapping(await requireSession(), message.payload) }); break;
        case "UPDATE_PROGRESS": sendResponse({ ok: true, data: await extensionApi.progress(await requireSession(), message.payload) }); break;
        case "CONFIRM_ANSWER": sendResponse({ ok: true, data: await extensionApi.confirmAnswer(await requireSession(), message.payload) }); break;
        case "CONFIRM_SUBMITTED": {
          const result = await extensionApi.confirmSubmitted(await requireSession(), message.payload);
          await chrome.storage.session.remove(STORAGE_KEY);
          sendResponse({ ok: true, data: result });
          break;
        }
        case "DOWNLOAD_RESUME": {
          const resume = await extensionApi.resume(await requireSession());
          const id = await chrome.downloads.download({
            url: `data:application/pdf;base64,${bytesToBase64(resume.bytes)}`,
            filename: filenameFromDisposition(resume.disposition),
            saveAs: true
          });
          sendResponse({ ok: true, data: { downloadId: id } });
          break;
        }
        case "DOWNLOAD_PORTFOLIO": {
          const portfolio = await extensionApi.portfolio(await requireSession());
          const id = await chrome.downloads.download({
            url: `data:application/pdf;base64,${bytesToBase64(portfolio.bytes)}`,
            filename: filenameFromDisposition(portfolio.disposition).replace("Recommended_Resume", "Project_Portfolio"),
            saveAs: true
          });
          sendResponse({ ok: true, data: { downloadId: id } });
          break;
        }
        case "GET_PREPARED_FILES": {
          const session = await requireSession();
          const payload = await extensionApi.payload(session);
          const resume = await extensionApi.resume(session);
          const files = [{
            kind: "RESUME",
            filename: payload.session.resume_filename || filenameFromDisposition(resume.disposition),
            mimeType: "application/pdf",
            base64: bytesToBase64(resume.bytes),
            versionId: payload.session.resume_version_id
          }];
          if (payload.portfolio?.id) {
            const portfolio = await extensionApi.portfolio(session);
            files.push({
              kind: "PORTFOLIO",
              filename: payload.portfolio.filename || filenameFromDisposition(portfolio.disposition),
              mimeType: "application/pdf",
              base64: bytesToBase64(portfolio.bytes),
              versionId: payload.portfolio.id
            });
          }
          sendResponse({ ok: true, data: files });
          break;
        }
        case "LOCAL_VISION_ANALYZE": {
          await requireSession();
          if (!sender.tab?.id || !sender.tab.url?.startsWith("https://")) throw new Error("Local vision must be requested by the connected secure application tab.");
          sendResponse({ ok: true, data: await analyzeVisibleApplicationLocally(sender.tab, message.payload) });
          break;
        }
        case "REVOKE_LOCAL_SESSION":
          await chrome.storage.session.remove(STORAGE_KEY);
          sendResponse({ ok: true });
          break;
        case "ENABLE_PORTAL_FOR_TAB": {
          await requireSession();
          const tab = await chrome.tabs.get(message.payload.tabId);
          if (!tab.url || tab.url !== message.payload.url) throw new Error("The active career portal changed before permission was granted.");
          const origin = portalOriginPattern(tab.url);
          const granted = await chrome.permissions.contains({ origins: [origin] });
          if (!granted) throw new Error("Portal access was not granted. Enable this career portal from the Apply Assistant controls.");
          const embeddedUrl = await openTrustedEmbeddedApplication(message.payload.tabId);
          await injectAssistant(message.payload.tabId);
          sendResponse({ ok: true, data: { origin: embeddedUrl ? portalOriginPattern(embeddedUrl) : origin, embeddedUrl } });
          break;
        }
        default: sendResponse({ ok: false, error: "Unsupported background action." });
      }
    } catch (error) {
      sendResponse({ ok: false, error: error instanceof Error ? error.message : "Extension operation failed." });
    }
  })();
  return true;
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete" || !tab.url?.startsWith("https://")) return;
  void getSession().then(async (session) => {
    if (!session) return;
    const origin = portalOriginPattern(tab.url!);
    if (!(await chrome.permissions.contains({ origins: [origin] }))) return;
    await injectAssistant(tabId).catch(() => undefined);
  });
});
