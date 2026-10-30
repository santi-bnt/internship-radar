"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { localAssistant, type AssistantPageState } from "@/lib/local-assistant";
import { splitScreenBounds } from "@/lib/split-screen";

export default function LocalApplicationControls({ connection, onClose }: {
  connection: { id: string; key: string }; onClose: () => void;
}) {
  const [state, setState] = useState<AssistantPageState | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [capture, setCapture] = useState<{ imageUrl: string; url: string; title: string; capturedAt: string } | null>(null);
  const [copiedField, setCopiedField] = useState("");
  const [visionStatus, setVisionStatus] = useState<{ available: boolean; model: string; reason: string } | null>(null);
  const [readingLocal, setReadingLocal] = useState(false);
  const [split, setSplit] = useState<{ popup: Window; root: HTMLElement } | null>(null);
  const page = useRef("");

  useEffect(() => {
    if (!split) return;
    const timer = window.setInterval(() => {
      if (split.popup.closed) setSplit(null);
    }, 400);
    return () => { window.clearInterval(timer); split.popup.close(); };
  }, [split]);

  async function openSplitScreen() {
    if (split && !split.popup.closed) { split.popup.focus(); return; }
    setError("");
    try {
      const bounds = splitScreenBounds(window.screen);
      const { left, top, width, height } = bounds.assistant;
      const popup = window.open("about:blank", "_blank", `popup=yes,left=${left},top=${top},width=${width},height=${height}`);
      if (!popup) throw new Error("Permite las ventanas emergentes de Internship Radar y pulsa Pantalla dividida otra vez.");
      popup.document.title = "Asistente de aplicación — Internship Radar";
      popup.document.documentElement.lang = "es";
      document.querySelectorAll("link[rel='stylesheet'], style").forEach((style) => {
        popup.document.head.appendChild(style.cloneNode(true));
      });
      popup.document.body.className = "local-assistant-split";
      const root = popup.document.createElement("main");
      popup.document.body.appendChild(root);
      setSplit({ popup, root });
      setBusy(true);
      await localAssistant(connection.key, `/sessions/${connection.id}/split-screen`, bounds.portal);
      popup.focus();
    } catch (caught) {
      setError(`${caught instanceof Error ? caught.message : "No se pudieron acomodar las ventanas."} Si acabas de actualizar, reinicia el asistente local. También puedes acomodarlas con Windows + flecha izquierda/derecha.`);
    } finally { setBusy(false); }
  }

  useEffect(() => {
    const controller = new AbortController();
    void localAssistant<AssistantPageState>(connection.key, `/sessions/${connection.id}/scan`, {}, controller.signal)
      .then((result) => { setState(result); page.current = result.pageObservation?.documentKey || result.applicationPageUrl || ""; })
      .catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Open the application in the local browser."); });
    return () => controller.abort();
  }, [connection]);

  async function action(name: string, body: Record<string, unknown> = {}) {
    setBusy(true); setReadingLocal(name === "analyze-local"); setError("");
    try {
      const next = await localAssistant<AssistantPageState>(connection.key, `/sessions/${connection.id}/${name}`, body,
        AbortSignal.timeout(name === "analyze-local" ? 195000 : 90000));
      if (name === "close") { onClose(); return; }
      const nextPage = next.pageObservation?.documentKey || next.applicationPageUrl || "";
      if (page.current !== nextPage) { setDrafts({}); setCapture(null); page.current = nextPage; }
      setState(next);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Check the local browser and try again."); }
    finally { setBusy(false); setReadingLocal(false); }
  }

  async function checkVision() {
    setBusy(true); setError("");
    try { setVisionStatus(await localAssistant(connection.key, `/sessions/${connection.id}/vision-status`, {})); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "No se pudo comprobar el motor de visión local."); }
    finally { setBusy(false); }
  }

  async function capturePage() {
    setBusy(true); setError("");
    try {
      setCapture(await localAssistant(connection.key, `/sessions/${connection.id}/capture`, {}));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "No se pudo capturar la página. Reinicia el asistente local."); }
    finally { setBusy(false); }
  }

  async function copyAnswer(fieldId: string, answer: string) {
    try {
      await (split?.popup.navigator || navigator).clipboard.writeText(answer);
      setCopiedField(fieldId);
    } catch { setError("Selecciona el texto de la respuesta y cópialo con Ctrl+C."); }
  }

  const controls = <section className="local-application-controls">
    <h3>Local application assistant</h3>
    <p>El asistente lee únicamente la ventana que abrió el navegador local. Abre ahí el formulario de aplicación y termina el inicio de sesión. Puedes comprobar la página con una captura y leer sus preguntas para obtener sugerencias.</p>
    {error && <div className="notice error" role="alert">{error}</div>}
    <div className="local-application-actions">
      {!split && <button className="button primary" disabled={busy} onClick={() => void openSplitScreen()}>Pantalla dividida: portal + asistente</button>}
      {split && <button className="button secondary" disabled={busy} onClick={() => setSplit(null)}>Volver al panel principal</button>}
      <button className="button secondary" disabled={busy} onClick={() => void action("scan")}>Refresh form</button>
      <button className="button secondary" disabled={busy} onClick={() => void capturePage()}>Ver captura de la página</button>
      <button className="button primary" disabled={busy} onClick={() => void action("analyze-local")}>Leer HTML + imagen (local)</button>
      {readingLocal && <button className="button secondary" onClick={() => {
        void localAssistant(connection.key, `/sessions/${connection.id}/cancel-analysis`, {})
          .catch(() => setError("No se pudo cancelar todavía. Puedes cerrar la ventana del navegador local."));
      }}>Cancelar lectura</button>}
      <button className="button secondary" disabled={busy} onClick={() => void checkVision()}>Comprobar visión local</button>
      {state?.isConfirmationPage && <button className="button primary" disabled={busy} onClick={() => void action("confirm-submitted")}>Confirm Applied</button>}
      <button className="button secondary" disabled={busy} onClick={() => void action("close")}>Close local browser</button>
    </div>
    {busy && <p role="status">{readingLocal ? "Leyendo el HTML y la captura con el modelo de este equipo. La primera lectura puede tardar mientras se carga el modelo…" : "Trabajando con el formulario actual…"}</p>}
    {visionStatus && <p className={`notice${visionStatus.available ? "" : " error"}`}>{visionStatus.model}: {visionStatus.reason}</p>}
    <p>La lectura y las sugerencias de HTML + imagen se procesan en tu equipo. Copia la respuesta revisada, adjunta el CV y avanza directamente en el portal. Tu perfil y los CV siguen guardados en tu cuenta de Internship Radar.</p>
    {state?.localVision && <p className="notice"><strong>Visión + HTML locales · {state.localVision.model}</strong><br />{state.localVision.message}<br />{state.localVision.domFields} campos del HTML · {state.localVision.imageQuestions} preguntas adicionales de la imagen. El texto sugerido proviene de evidencia del perfil/CV; el modelo no inventa cualificaciones.</p>}
    {state && <p>{state.currentSection} · {state.fields.length} fields detected{state.isReviewPage ? " · Ready for your final review and manual submission" : ""}</p>}
    {state?.pageObservation && <div className="notice local-page-observation">
      <strong>Página que está leyendo: {state.pageObservation.title}</strong>
      <span>{state.pageObservation.url}</span>
      <span>{state.pageObservation.framesScanned} documentos revisados · {state.fields.length} campos detectados · {new Date(state.pageObservation.readAt).toLocaleTimeString()}</span>
      {state.pageObservation.unreadableFrames > 0 && <span>{state.pageObservation.unreadableFrames} documentos no se pudieron leer.</span>}
      {state.pageObservation.readOnly && <span>Solo lectura: puedes revisar y copiar sugerencias. La carga de archivos y las acciones se hacen directamente en el portal.</span>}
    </div>}
    {state?.lastActionMessage && !state.fields.length && <p className="notice" role="status">{state.lastActionMessage}</p>}
    {capture && <figure className="local-page-capture">
      <figcaption>Vista previa local: {capture.title} · {new Date(capture.capturedAt).toLocaleTimeString()}. Usa “Leer HTML + imagen” para analizar una captura con el modelo local. Las imágenes no se envían a servicios remotos.</figcaption>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={capture.imageUrl} alt="Página actualmente abierta en el navegador del asistente local" />
    </figure>}
    {state && (() => {
      const resumeField = state.fields.find((field) => field.controlType === "file"
        && /resume|curriculum|\bcv\b/i.test(`${field.label} ${field.fieldId}`));
      if (!resumeField) return <p className="notice">No detecto la carga de CV en esta sección. Sube el PDF directamente en el navegador local cuando aparezca el campo y pulsa “Refresh form” para confirmar.</p>;
      if (resumeField.currentValue) return <p className="notice">CV que muestra el portal: {String(resumeField.currentValue)}</p>;
      return <p className="notice">Adjunta el PDF manualmente en el campo del portal y luego pulsa “Refresh form”. Así puedes continuar aunque la carga automática no funcione.</p>;
    })()}
    {state?.pendingQuestions.map((question) => <p className="notice" key={question.questionKey}>{question.question} — select your answer directly in the browser.</p>)}
    {state?.fields.filter((field) => !["file", "password", "hidden"].includes(field.controlType)).map((field) => {
      const decision = state.agentDecisions.find((item) => item.field_id === field.fieldId);
      const suggested = decision?.selected_value ?? decision?.selected_option ?? "";
      const suggestionText = typeof suggested === "boolean" ? suggested ? "Yes" : "No"
        : typeof suggested === "string" || typeof suggested === "number" ? String(suggested)
        : Array.isArray(suggested) ? suggested.filter((value) => typeof value === "string").join(", ") : "";
      const answer = drafts[field.fieldId] ?? suggestionText;
      return <div className="local-application-question" key={field.fieldId}>
        <div className="local-application-question-prompt">
          <strong>{field.label}{field.required ? " *" : ""}</strong>
          {field.nearbyText && field.nearbyText !== field.label && <small>{field.nearbyText}</small>}
        </div>
        <div className="local-application-question-answer">
          {!decision ? <p>Pulsa “Leer HTML + imagen (local)” para analizar esta pregunta.</p> : <>
            <label>Respuesta sugerida · revísala antes de usarla
              <textarea rows={4} value={answer} maxLength={field.maxlength} onChange={(event) => { setCopiedField(""); setDrafts((current) => ({ ...current, [field.fieldId]: event.target.value })); }} />
            </label>
            <small>{answer.length}{field.maxlength ? ` / ${field.maxlength}` : ""} caracteres · {decision.reason_summary}</small>
            {!answer && <small>Falta una respuesta confirmada. Contesta esta pregunta directamente en el portal.</small>}
            <button className="button secondary" disabled={busy || !answer.trim()} onClick={() => void copyAnswer(field.fieldId, answer)}>{copiedField === field.fieldId ? "Respuesta copiada" : "Copiar respuesta"}</button>
            {!state.pageObservation?.readOnly && ["text", "textarea"].includes(field.controlType) && <button className="button secondary" disabled={busy || !answer.trim() || decision.action !== "GENERATE_REVIEW" || state.isReviewPage || Boolean(state.assessmentType)}
              onClick={() => void action("answer", { fieldId: field.fieldId, answer })}>Revisar y colocar en el formulario</button>}
          </>}
        </div>
      </div>;
    })}
  </section>;
  if (!split) return controls;
  return <>
    <p className="notice">El asistente está abierto en la ventana lateral. Mantén esta página abierta para conservar la sesión.</p>
    <button className="button secondary" onClick={() => split.popup.focus()}>Ver asistente</button>
    <button className="button secondary" onClick={() => setSplit(null)}>Traer asistente aquí</button>
    {createPortal(controls, split.root)}
  </>;
}
