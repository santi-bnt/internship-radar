import type { RuntimeMessage } from "../shared/messages";

type WebBridgeMessage =
  | { source?: string; type: "PING_APPLICATION_ASSISTANT" }
  | ({ source?: string } & Extract<RuntimeMessage, { type: "CONNECT_APPLICATION_SESSION" }>);

window.addEventListener("message", (event: MessageEvent) => {
  if (event.source !== window || event.origin !== window.location.origin) return;
  const message = event.data as WebBridgeMessage;
  if (message?.source !== "internship-radar-web") return;
  if (message.type === "PING_APPLICATION_ASSISTANT") {
    chrome.runtime.sendMessage({ type: "PING" }, (response) => {
      const runtimeError = chrome.runtime.lastError?.message;
      window.postMessage(
        { source: "internship-radar-extension", type: "APPLICATION_ASSISTANT_PONG", ok: Boolean(response?.ok) && !runtimeError, error: runtimeError || response?.error || "", data: response?.data },
        window.location.origin
      );
    });
    return;
  }
  if (message.type !== "CONNECT_APPLICATION_SESSION") return;
  const payload = message.payload;
  if (!payload || !Number.isInteger(payload.sessionId) || typeof payload.token !== "string" || typeof payload.apiBaseUrl !== "string") return;
  chrome.runtime.sendMessage({ type: "CONNECT_APPLICATION_SESSION", payload }, (response) => {
    const runtimeError = chrome.runtime.lastError?.message;
    window.postMessage(
      { source: "internship-radar-extension", type: "APPLICATION_SESSION_CONNECTION_RESULT", ok: Boolean(response?.ok) && !runtimeError, error: runtimeError || response?.error || "", data: response?.data },
      window.location.origin
    );
  });
});
