import { afterEach, describe, expect, it, vi } from "vitest";
import { LocalVisionClient, localModelConfig, sanitizedFormHtml } from "../src/vision";
import { evidenceAnswer, localCandidateEvidence } from "../src/local-evidence";
import { makePayload } from "../../extension/tests/fixtures";

const question = () => ({ label: "Describe your project experience", dom_field_id: "why", control_type: "textarea", options: [],
  required: true, confidence: 0.95, canonical_field: "PROJECTS", evidence_ids: ["project:0"] });
const input = () => ({ image: "LOCAL_JPEG_BYTES", html: '<form><label>Project experience</label></form>',
  fields: [{ id: "why", label: "Describe your project experience" }], evidence: localCandidateEvidence(makePayload("GENERIC")) });
const json = (data: unknown) => new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("device-local HTML and vision inference", () => {
  it("sends the image and sanitized form only to loopback Ollama using a stateless structured request", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json({ capabilities: ["completion", "vision"] }))
      .mockResolvedValueOnce(json({ message: { content: JSON.stringify({ screen_state: "APPLICATION", questions: [question()] }) } }));
    vi.stubGlobal("fetch", fetcher);
    expect((await new LocalVisionClient().interpret(input(), AbortSignal.timeout(1000))).questions).toHaveLength(1);
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(["http://127.0.0.1:11434/api/show", "http://127.0.0.1:11434/api/chat"]);
    const body = JSON.parse(fetcher.mock.calls[1][1].body);
    expect(body.messages[1].images).toEqual(["LOCAL_JPEG_BYTES"]);
    expect(body.messages[1].content).toContain("<form>");
    expect(body.format.properties.questions).toBeTruthy();
    expect(body.messages).toHaveLength(2);
    expect(fetcher.mock.calls[1][1]).toMatchObject({ redirect: "error", credentials: "omit" });
    expect(JSON.stringify(body)).not.toMatch(/scoped-session-token|Authorization/);
  });

  it.each(["http://localhost:11434", "https://example.com", "http://127.0.0.1.example.com", "http://user:secret@127.0.0.1:11434", "http://127.0.0.1:11434/redirect", "http://169.254.169.254"])("rejects non-fixed local endpoint %s", (base) => {
    expect(() => localModelConfig(base)).toThrow();
  });
  it.each(["gemma3:cloud", "https://remote.example/model", "ollama.com/remote"])("rejects cloud model name %s", (model) => {
    expect(() => localModelConfig(undefined, model)).toThrow();
  });
  it.each([{ capabilities: ["completion"] }, { capabilities: ["vision"], remote_model: "remote" }])("rejects text-only or remotely hosted aliases", async (show) => {
    const fetcher = vi.fn().mockResolvedValue(json(show));
    vi.stubGlobal("fetch", fetcher);
    await expect(new LocalVisionClient().interpret(input(), AbortSignal.timeout(1000))).rejects.toThrow("en este equipo");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it.each([{ evidence_ids: ["invented:evidence"] }, { dom_field_id: "invented:field" }, { confidence: 5 }])("rejects hallucinated references or invalid confidence", async (change) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ capabilities: ["vision"] }))
      .mockResolvedValueOnce(json({ message: { content: JSON.stringify({ screen_state: "APPLICATION", questions: [{ ...question(), ...change }] }) } })));
    await expect(new LocalVisionClient().interpret(input(), AbortSignal.timeout(1000))).rejects.toThrow("no verificados");
  });
  it("rejects malformed and oversized responses without a remote fallback", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json({ capabilities: ["vision"] }))
      .mockResolvedValueOnce(new Response("x".repeat(1_500_001), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetcher);
    await expect(new LocalVisionClient().interpret(input(), AbortSignal.timeout(1000))).rejects.toThrow("límite");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("does not forward redirects or use any external endpoint when inference fails", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("redirect or unreachable"));
    vi.stubGlobal("fetch", fetcher);
    await expect(new LocalVisionClient().interpret(input(), AbortSignal.timeout(1000))).rejects.toThrow("modelo local");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("serializes an allowlisted HTML outline without interpreting markup from the page", () => {
    const html = sanitizedFormHtml([{ fieldId: 'id"evil', label: '<script>submit()</script>', controlType: "text", availableOptions: [] }]);
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });
});

describe("local verified candidate answers", () => {
  it("excludes planned, ineligible, unknown and non-resume project claims", () => {
    const payload = makePayload("GENERIC");
    payload.session.project_experience_json = [
      { name: "Planned", evidence_strength: "PLANNED_ONLY", resume_selection: { bullets: ["Future feature"] } },
      { name: "Excluded", is_resume_eligible: false, resume_selection: { bullets: ["Do not use"] } },
      { name: "Unknown", description: "Unverified accomplishment" },
    ];
    expect(localCandidateEvidence(payload).filter((item) => item.kind === "PROJECT")).toHaveLength(0);
  });
  it("uses only the selected session's project and resume skills", () => {
    const payload = makePayload("GENERIC");
    const evidence = localCandidateEvidence(payload);
    const answer = evidenceAnswer(question(), "why", evidence, "gemma3:4b");
    expect(answer.selected_value).toContain("academic and personal projects");
    expect(answer.selected_value).toContain("FastAPI");
    expect(answer.selected_value).not.toMatch(/professional employment|worked at|Java expertise/);
    expect(evidence.filter((item) => item.kind === "SKILL").map((item) => item.text)).toEqual(["Python", "Git"]);
    expect(evidence.some((item) => item.text === "REST APIs")).toBe(false);
  });
  it("never converts project references into professional employment or answers legal blockers", () => {
    const evidence = localCandidateEvidence(makePayload("GENERIC"));
    expect(evidenceAnswer({ ...question(), canonical_field: "WORK" }, "why", evidence, "gemma3:4b").selected_value).toBe("");
    const legal = evidenceAnswer({ ...question(), label: "Are you authorized to work in the US?" }, "why", evidence, "gemma3:4b");
    expect(legal.action).toBe("CONFIRM");
    expect(legal.selected_value).toBe("");
  });
  it("does not invent Java evidence or use a different candidate's facts", () => {
    const a = makePayload("GENERIC"), b = makePayload("GENERIC");
    b.profile.contact.full_name = "Another candidate";
    b.session.project_experience_json = [];
    b.session.selected_projects_json = [];
    b.resume.selected_skills = [];
    const bEvidence = localCandidateEvidence(b);
    expect(bEvidence.some((item) => item.text.includes(a.profile.contact.full_name))).toBe(false);
    expect(bEvidence.some((item) => item.kind === "PROJECT")).toBe(false);
    const missing = evidenceAnswer({ ...question(), label: "Java experience?", canonical_field: "SKILLS", evidence_ids: [] }, "java", bEvidence, "gemma3:4b");
    expect(missing.action).toBe("MANUAL_ONLY");
    expect(missing.selected_value).toBe("");
  });
});
