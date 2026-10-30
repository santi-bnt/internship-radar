import type { RuntimeMessage } from "../shared/messages";
import type { AssistantPageState } from "../shared/types";

/** Keep drafts and focus while the side panel polls the portal for updates. */
export class ApplicationQuestions {
  private scope = "";
  private signature = "";
  private drafts = new Map<string, string>();

  constructor(
    private readonly container: HTMLElement,
    private readonly apply: (message: RuntimeMessage) => Promise<void>,
  ) {}

  render(state: AssistantPageState, pageUrl: string): void {
    const scope = `${state.applicationSessionId ?? ""}:${state.applicationPageUrl || pageUrl}`;
    if (scope !== this.scope || !state.connected) {
      this.scope = scope;
      this.signature = "";
      this.drafts.clear();
      this.container.replaceChildren();
    }
    if (!state.connected) return;
    const questions = state.fields.flatMap((field) => {
      const decision = state.agentDecisions.find((item) => item.field_id === field.fieldId);
      if (!decision || !["JOB_SPECIFIC_TEXT", "EXPERIENCE_QUESTION", "UNKNOWN"].includes(decision.question_category)) return [];
      if (!["textarea", "text"].includes(field.controlType)) return [];
      return [{ field, decision }];
    });
    const signature = JSON.stringify([questions, state.paused, state.isReviewPage, state.assessmentType]);
    if (this.signature === signature) return;
    this.signature = signature;
    this.container.replaceChildren(...questions.map(({ field, decision }) => {
      const card = document.createElement("article");
      card.className = "question-card";
      const label = document.createElement("label");
      label.textContent = `${field.label}${field.required ? " *" : ""}`;
      const editor = document.createElement("textarea");
      editor.rows = 6;
      editor.setAttribute("aria-label", field.label);
      if (field.maxlength) editor.maxLength = field.maxlength;
      editor.value = this.drafts.get(field.fieldId)
        ?? String(field.currentValue || decision.selected_value || "");
      const length = document.createElement("small");
      const updateLength = () => { length.textContent = `${editor.value.length}${field.maxlength ? ` / ${field.maxlength}` : ""} characters`; };
      updateLength();
      editor.addEventListener("input", () => { this.drafts.set(field.fieldId, editor.value); updateLength(); });
      label.append(editor);
      const reason = document.createElement("p");
      reason.textContent = decision.reason_summary;
      if (decision.evidence_ids.length) reason.textContent += ` Evidence: ${decision.evidence_ids.join(", ")}.`;
      const actions = document.createElement("div");
      actions.className = "actions";
      const copy = document.createElement("button");
      copy.textContent = "Copy answer";
      copy.addEventListener("click", () => {
        void navigator.clipboard.writeText(editor.value).then(() => { copy.textContent = "Copied"; }).catch(() => {
          editor.focus(); editor.select(); copy.textContent = "Select and copy";
        });
      });
      const use = document.createElement("button");
      use.className = "primary";
      use.textContent = "Use reviewed answer";
      use.disabled = decision.action !== "GENERATE_REVIEW" || state.paused || state.isReviewPage || Boolean(state.assessmentType);
      use.addEventListener("click", async () => {
        if (!editor.value.trim()) { editor.focus(); return; }
        this.drafts.set(field.fieldId, editor.value);
        use.disabled = true;
        try { await this.apply({ type: "APPLY_REVIEWED_ANSWER", payload: { fieldId: field.fieldId, answer: editor.value } }); }
        finally { use.disabled = false; }
      });
      actions.append(copy, use);
      card.append(label, length, reason, actions);
      return card;
    }));
  }
}
