import { beforeEach, describe, expect, it, vi } from "vitest";

import { AmazonJobsAdapter } from "../src/content/adapters/amazon/AmazonJobsAdapter";
import { GenericApplicationAdapter } from "../src/content/adapters/generic/GenericApplicationAdapter";
import { GreenhouseAdapter } from "../src/content/adapters/greenhouse/GreenhouseAdapter";
import { MicrosoftCareersAdapter } from "../src/content/adapters/microsoft/MicrosoftCareersAdapter";
import { OracleCareersAdapter } from "../src/content/adapters/oracle/OracleCareersAdapter";
import { WorkdayAdapter } from "../src/content/adapters/workday/WorkdayAdapter";
import { ApplicationAssistantCore } from "../src/content/ApplicationAssistantCore";
import { detectPortal } from "../src/shared/portalDetection";
import { fieldPolicy, isFinalSubmitText } from "../src/shared/policies";
import { makePayload } from "./fixtures";

describe("multi-portal Apply Assistant", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("routes Intel and GE through the shared Workday adapter", () => {
    expect(detectPortal("https://intel.wd1.myworkdayjobs.com/job/REQ-1234", "Intel").portalType).toBe("WORKDAY");
    expect(detectPortal("https://geaerospace.wd5.myworkdayjobs.com/job/R-12345", "GE Aerospace").portalType).toBe("WORKDAY");
  });

  it("does not mistake a generic data-testid application form for Microsoft on another company", () => {
    document.body.innerHTML = `<form data-testid="application-form"><input name="first_name" /></form>`;
    expect(detectPortal("https://careers.example.com/apply/123", "Example").portalType).toBe("GENERIC");
    expect(detectPortal("https://careers.microsoft.com/apply/123", "Microsoft").portalType).toBe("MICROSOFT_CAREERS");
  });

  it("detects a Greenhouse-backed Zipline form from DOM instead of company hostname alone", () => {
    document.body.innerHTML = `<form id="application_form"><input name="first_name" /></form>`;
    const detection = detectPortal("https://www.zipline.com/open-roles/embedded", "Zipline");
    expect(detection.portalType).toBe("GREENHOUSE");
    expect(detection.confidence).toBeGreaterThan(0.9);
  });

  it("recognizes the current Greenhouse embedded application renderer", () => {
    document.body.innerHTML = `<form id="application-form" class="application--form" action="/embed/job_app?for=flyzipline&token=7904518003"><div class="field-wrapper"><div class="input-wrapper"><label for="first_name">First Name</label><input id="first_name" /></div></div></form>`;
    const detection = detectPortal(
      "https://job-boards.greenhouse.io/embed/job_app?for=flyzipline&token=7904518003",
      "Zipline",
    );
    expect(detection.portalType).toBe("GREENHOUSE");
    expect(detection.confidence).toBe(0.99);
    expect(new GreenhouseAdapter().review(makePayload("GREENHOUSE", "Zipline")).supportStatus).toBe("SUPPORTED");
  });

  it("maps common Zipline Greenhouse contact fields and reuses confirmed legal answers", async () => {
    document.body.innerHTML = `
      <form id="application_form">
        <div class="field"><label for="first">First Name</label><input id="first" /></div>
        <div class="field"><label for="email">Email</label><input id="email" /></div>
        <div class="field"><label for="linkedin">LinkedIn</label><input id="linkedin" /></div>
        <div class="field"><label for="sponsor">Will you require visa sponsorship?</label><select id="sponsor"><option></option><option>Yes</option><option>No</option></select></div>
      </form>`;
    const adapter = new GreenhouseAdapter();
    const payload = makePayload("GREENHOUSE", "Zipline");
    const result = await adapter.fillThisPage(payload);
    expect((document.getElementById("first") as HTMLInputElement).value).toBe("Santiago");
    expect((document.getElementById("email") as HTMLInputElement).value).toBe("candidate@example.com");
    expect((document.getElementById("linkedin") as HTMLInputElement).value).toContain("linkedin.com");
    expect((document.getElementById("sponsor") as HTMLSelectElement).value).toBe("Yes");
    expect(result.filled).toBe(4);
    expect(adapter.review(payload).pendingQuestions).toEqual([]);
  });

  it("requires confirmation for GE government questions", () => {
    document.body.innerHTML = `<div data-automation-id="formField"><label for="gov">Are you currently or formerly employed by a government?</label><select id="gov"><option></option><option>Yes</option><option>No</option></select></div>`;
    const payload = makePayload("WORKDAY", "GE Aerospace");
    payload.company_policy.known_question_aliases = { GOVERNMENT_EMPLOYEE: ["currently or formerly employed by a government"] };
    const questions = new WorkdayAdapter().review(payload).pendingQuestions;
    expect(questions[0]?.questionKey).toBe("GOVERNMENT_EMPLOYEE");
  });

  it("requires confirmation for Intel compliance questions", () => {
    document.body.innerHTML = `<div data-automation-id="formField"><label for="former">Were you previously employed by Intel?</label><select id="former"><option></option><option>Yes</option><option>No</option></select></div>`;
    const payload = makePayload("WORKDAY", "Intel");
    payload.company_policy.known_question_aliases = { FORMER_INTEL_EMPLOYEE: ["previously employed by intel"] };
    const question = new WorkdayAdapter().review(payload).pendingQuestions[0];
    expect(question?.questionKey).toBe("FORMER_INTEL_EMPLOYEE");
    expect((document.getElementById("former") as HTMLSelectElement).value).toBe("");
  });

  it("does not overwrite a conflicting Microsoft saved profile without a choice", async () => {
    document.body.innerHTML = `<form data-testid="application-form"><div data-testid="field"><label for="grad">Expected graduation date</label><input id="grad" value="2026-06-01" /></div></form>`;
    const adapter = new MicrosoftCareersAdapter();
    const payload = makePayload("MICROSOFT_CAREERS", "Microsoft");
    await adapter.fillThisPage(payload);
    expect((document.getElementById("grad") as HTMLInputElement).value).toBe("2026-06-01");
    const conflict = adapter.review(payload).fields.find((field) => field.label.includes("graduation"))?.conflict;
    expect(conflict?.classification).toBe("CRITICAL_CONFLICT");
    expect(await adapter.resolveFieldConflict("EXPECTED_GRADUATION_DATE", true, payload)).toBe(true);
    expect((document.getElementById("grad") as HTMLInputElement).value).toBe("June 2028");
  });

  it("keeps the user's explicit choice to retain a saved portal value", async () => {
    document.body.innerHTML = `<form data-testid="application-form"><div data-testid="field"><label for="grad">Expected graduation date</label><input id="grad" value="2026-06-01" /></div></form>`;
    const adapter = new MicrosoftCareersAdapter();
    const payload = makePayload("MICROSOFT_CAREERS", "Microsoft");
    await adapter.fillThisPage(payload);
    expect(await adapter.resolveFieldConflict("EXPECTED_GRADUATION_DATE", false, payload)).toBe(true);
    await adapter.fillThisPage(payload);
    expect((document.getElementById("grad") as HTMLInputElement).value).toBe("2026-06-01");
    expect(adapter.review(payload).fields.find((field) => field.label.includes("graduation"))?.conflict).toBeUndefined();
  });

  it("fills safe Amazon profile data and pauses for an assessment", async () => {
    document.body.innerHTML = `<form data-test-id="application-form"><div data-test-id="field"><label for="email">Email</label><input id="email" /></div></form>`;
    const adapter = new AmazonJobsAdapter();
    const payload = makePayload("AMAZON_JOBS", "Amazon / AWS");
    expect((await adapter.fillThisPage(payload)).filled).toBe(1);
    document.body.insertAdjacentHTML("afterbegin", `<h1>Coding assessment</h1><p>Complete your online assessment.</p>`);
    expect(adapter.detectAssessment()).toBe("CODING_ASSESSMENT");
    expect((await adapter.fillThisPage(payload)).filled).toBe(0);
    expect(adapter.review(payload).safeAutofillPausedReason).toContain("Assessment");
  });

  it("normalizes Oracle custom questions and fails safely after an unrecognized portal change", () => {
    document.body.innerHTML = `<div data-oj-binding-provider="none"><div class="form-field"><label for="auth">Are you authorized to work in this country?</label><select id="auth"><option></option><option>Yes</option><option>No</option></select></div></div>`;
    const adapter = new OracleCareersAdapter();
    const payload = makePayload("ORACLE_CAREERS", "Oracle");
    expect(adapter.review(payload).fields.find((field) => field.normalizedKey === "WORK_AUTHORIZATION_CURRENT_COUNTRY")?.policy).toBe("AUTO_FILL_REVIEW_REQUIRED");
    document.body.innerHTML = `<form><label for="name">Full Name</label><input id="name" /></form>`;
    const changed = new OracleCareersAdapter().review(payload);
    expect(changed.supportStatus).toBe("PORTAL_CHANGED");
    expect(changed.paused).toBe(true);
  });

  it("uses country-aware authorization and sponsorship answers for a Mexico job", async () => {
    document.body.innerHTML = `<form id="application_form">
      <label for="auth-mx">Are you legally authorized to work in Mexico?</label>
      <select id="auth-mx"><option></option><option>Yes</option><option>No</option></select>
      <label for="sponsor-mx">Will you require sponsorship to work in Mexico?</label>
      <select id="sponsor-mx"><option></option><option>Yes</option><option>No</option></select>
    </form>`;
    const payload = makePayload("GREENHOUSE", "Example Mexico Company");
    const adapter = new GreenhouseAdapter();
    const result = await adapter.fillThisPage(payload);
    expect(result).toEqual({ filled: 2, reviewed: 2 });
    expect((document.getElementById("auth-mx") as HTMLSelectElement).value).toBe("Yes");
    expect((document.getElementById("sponsor-mx") as HTMLSelectElement).value).toBe("No");
    expect(adapter.review(payload).legalReview).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "Mexico work authorized", value: "Yes" }),
      expect.objectContaining({ label: "Mexico sponsorship required", value: "No" }),
    ]));
  });

  it("limits the generic adapter to high-confidence safe fields", async () => {
    document.body.innerHTML = `<form>
      <div class="field"><label for="name">Full Name</label><input id="name" /></div>
      <div class="field"><label for="school">University</label><input id="school" /></div>
      <div class="field"><label for="salary">Salary expectation</label><input id="salary" /></div>
      <div class="field"><label for="legal">Describe any legal restrictions</label><textarea id="legal"></textarea></div>
    </form>`;
    const adapter = new GenericApplicationAdapter();
    const result = await adapter.fillThisPage(makePayload("GENERIC", "Unknown Company"));
    expect(result.filled).toBe(2);
    expect((document.getElementById("salary") as HTMLInputElement).value).toBe("");
    expect((document.getElementById("legal") as HTMLTextAreaElement).value).toBe("");
    const unknown = adapter.review(makePayload("GENERIC", "Unknown Company")).fields.find((field) => field.label.includes("legal"));
    expect(unknown?.normalizedKey).toBe("UNKNOWN");
    expect(unknown?.policy).toBe("MANUAL_ONLY");
  });

  it("uses role-specific session projects instead of a company-wide hardcoded project", async () => {
    document.body.innerHTML = `<form id="application_form"><div class="field"><label for="projects">Relevant project experience</label><textarea id="projects"></textarea></div></form>`;
    const software = makePayload("GREENHOUSE", "Zipline");
    await new GreenhouseAdapter().fillThisPage(software);
    expect((document.getElementById("projects") as HTMLTextAreaElement).value).toContain("Internship Radar");
    const embedded = makePayload("GREENHOUSE", "Zipline");
    embedded.session.project_experience_json = [{ name: "FreeRTOS System", resume_selection: { bullets: ["Built deterministic RTOS tasks."] } }];
    await new GreenhouseAdapter().fillThisPage(embedded);
    expect((document.getElementById("projects") as HTMLTextAreaElement).value).toContain("FreeRTOS System");
  });

  it("uses only the job-ranked verified skills for a structured portal", async () => {
    document.body.innerHTML = `<div data-automation-id="formField"><label for="skills">Skills</label><input id="skills" /></div><div role="option">REST APIs</div><button>Add</button>`;
    const payload = makePayload("WORKDAY", "Intel");
    payload.resume.selected_skills = ["REST APIs"];
    const typed: string[] = [];
    document.getElementById("skills")!.addEventListener("input", (event) => typed.push((event.target as HTMLInputElement).value));
    await new WorkdayAdapter().fillThisPage(payload);
    expect(typed).toContain("REST APIs");
    expect(typed).not.toContain("Python");
  });

  it("labels academic projects honestly when a portal only offers Work Experience", async () => {
    document.body.innerHTML = `<form id="application_form"><div class="field"><label for="experience">Work Experience</label><textarea id="experience"></textarea></div></form>`;
    const payload = makePayload("GREENHOUSE", "Example");
    await new GreenhouseAdapter().fillThisPage(payload);
    const value = (document.getElementById("experience") as HTMLTextAreaElement).value;
    expect(value).toContain("Student Software Developer — Academic & Personal Projects");
    expect(value).toContain("Tecnológico de Monterrey / Personal Projects");
    expect(value).toContain("Academic and personal software projects; not professional employment.");
    expect(value).not.toContain("Example — Internship Radar");
  });

  it("ignores password, CAPTCHA, MFA, and electronic-signature fields on every portal", () => {
    expect(fieldPolicy("Career account password", "password").policy).toBe("MANUAL_ONLY");
    expect(fieldPolicy("CAPTCHA response").policy).toBe("MANUAL_ONLY");
    expect(fieldPolicy("MFA verification code").policy).toBe("MANUAL_ONLY");
    expect(fieldPolicy("Electronic signature").policy).toBe("MANUAL_ONLY");
  });

  it.each([
    ["Workday", new WorkdayAdapter()], ["Greenhouse", new GreenhouseAdapter()],
    ["Microsoft", new MicrosoftCareersAdapter()], ["Amazon", new AmazonJobsAdapter()],
    ["Oracle", new OracleCareersAdapter()], ["Generic", new GenericApplicationAdapter()]
  ])("blocks final Submit in the %s adapter", async (_name, adapter) => {
    document.body.innerHTML = `<h1>Review your application</h1><button id="submit">Complete Application</button>`;
    const clicked = vi.fn();
    document.getElementById("submit")!.addEventListener("click", clicked);
    expect(adapter.isReviewPage()).toBe(true);
    expect(await adapter.continuePage(0)).toBe(false);
    expect(clicked).not.toHaveBeenCalled();
  });

  it("blocks common final-action wording without treating unrelated buttons as final submission", async () => {
    document.body.innerHTML = `<button id="filter">Apply filters</button><button id="submit">Submit your application</button>`;
    const adapter = new GenericApplicationAdapter();
    const submit = vi.fn();
    const filter = vi.fn();
    document.getElementById("submit")!.addEventListener("click", submit);
    document.getElementById("filter")!.addEventListener("click", filter);
    expect(isFinalSubmitText("Submit your application")).toBe(true);
    expect(isFinalSubmitText("Apply filters")).toBe(false);
    expect(await adapter.continuePage(0)).toBe(false);
    expect(submit).not.toHaveBeenCalled();
    expect(filter).not.toHaveBeenCalled();
  });

  it("fills a single-page Greenhouse form even though its manual Submit button is visible", async () => {
    document.body.innerHTML = `
      <form id="application-form" class="application--form" action="/embed/job_app?for=flyzipline&token=7904518003">
        <div class="field"><label for="first_name">First Name</label><input id="first_name" name="first_name" /></div>
        <div class="field"><label for="last_name">Last Name</label><input id="last_name" name="last_name" /></div>
        <div class="field"><label for="email">Email</label><input id="email" name="email" /></div>
        <button id="submit" type="submit">Submit Application</button>
      </form>`;
    const submitted = vi.fn((event: Event) => event.preventDefault());
    document.getElementById("submit")!.addEventListener("click", submitted);
    const core = new ApplicationAssistantCore(makePayload("GREENHOUSE", "Zipline"));

    expect(core.review().isReviewPage).toBe(false);
    expect(await core.fillThisPage()).toEqual({ filled: 3, reviewed: 0 });
    expect((document.getElementById("first_name") as HTMLInputElement).value).toBe("Santiago");
    expect((document.getElementById("last_name") as HTMLInputElement).value).toBe("Example");
    expect((document.getElementById("email") as HTMLInputElement).value).toBe("candidate@example.com");
    expect(await core.continuePage(0)).toBe(false);
    expect(submitted).not.toHaveBeenCalled();
  });

  it("completes the current Zipline Greenhouse fields and reaches review without submitting", async () => {
    document.body.innerHTML = `
      <form id="application-form" class="application--form" action="/embed/job_app?for=flyzipline&token=7904518003">
        <h1>Aerodynamics Intern (Summer 2027)</h1>
        <label for="first_name">First Name*</label><input id="first_name" aria-required="true" />
        <label for="last_name">Last Name*</label><input id="last_name" aria-required="true" />
        <label for="email">Email*</label><input id="email" aria-required="true" />
        <label for="phone">Phone*</label><input id="phone" aria-required="true" />
        <div class="select__container"><label for="country">Country*</label><input id="country" role="combobox" aria-required="true" /><div class="test-options"><div role="option">Mexico +52</div></div></div>
        <div class="select__container"><label for="candidate-location">Location (City)*</label><input id="candidate-location" role="combobox" aria-required="true" /><div class="test-options"><div role="option">Guadalajara, Jalisco, Mexico</div></div></div>
        <div role="group" aria-labelledby="resume-label"><div id="resume-label">Resume/CV*</div><input id="resume" type="file" aria-required="true" style="display:none" /></div>
        <div class="select__container"><label for="end-month--0">End date month*</label><input id="end-month--0" role="combobox" aria-required="true" /><div class="test-options"><div role="option">June</div></div></div>
        <label for="end-year--0">End date year*</label><input id="end-year--0" type="number" aria-required="true" />
        <label for="linkedin">LinkedIn Profile</label><input id="linkedin" />
        <div class="select__container"><label for="source">Tell us how you heard about Zipline and this job!*</label><input id="source" role="combobox" aria-required="true" /><div class="test-options"><div role="option">Google Search</div></div></div>
        <div class="select__container"><label for="summer">Are you available for a full-time onsite internship this Summer (May/June - August/September)?*</label><input id="summer" role="combobox" aria-required="true" /><div class="test-options"><div role="option">Yes</div><div role="option">No</div></div></div>
        <div class="select__container"><label for="combined">Would you be interested and available for a combined Spring and Summer internship (January to August or September)?*</label><input id="combined" role="combobox" aria-required="true" /><div class="test-options"><div role="option">Yes</div><div role="option">No</div></div></div>
        <label for="project">Briefly summarize a relevant aerodynamic project*</label><textarea id="project" aria-required="true"></textarea>
        <div role="group" aria-labelledby="portfolio-label"><div id="portfolio-label">[Optional] Submit your project portfolio here</div><input id="portfolio" type="file" style="display:none" /></div>
        <fieldset aria-required="true">
          <legend>Please provide details on your current work authorization status in the United States:</legend>
          <input id="authorized" name="authorization" type="checkbox" aria-required="true" /><label for="authorized">I am legally authorized to work for any employer in the United States</label>
          <input id="sponsor" name="authorization" type="checkbox" aria-required="true" /><label for="sponsor">I require, or in the future will require sponsorship to obtain work authorization in the country in which this position is based</label>
          <input id="not-authorized" name="authorization" type="checkbox" aria-required="true" /><label for="not-authorized">I am not currently authorized to work in the United States.</label>
        </fieldset>
        <button id="submit" type="submit">Submit Application</button>
      </form>`;
    for (const container of document.querySelectorAll<HTMLElement>(".select__container")) {
      const input = container.querySelector<HTMLInputElement>("[role='combobox']")!;
      const options = container.querySelector<HTMLElement>(".test-options")!;
      options.style.display = "none";
      input.addEventListener("click", () => {
        document.querySelectorAll<HTMLElement>(".test-options").forEach((item) => { item.style.display = "none"; });
        options.style.display = "block";
      });
      options.querySelectorAll<HTMLElement>("[role='option']").forEach((option) => option.addEventListener("click", () => {
        let selected = container.querySelector<HTMLElement>(".select__single-value");
        if (!selected) {
          selected = document.createElement("div");
          selected.className = "select__single-value";
          container.append(selected);
        }
        selected.textContent = option.textContent?.startsWith("Mexico") ? "+52" : option.textContent;
        input.value = "";
        options.style.display = "none";
      }));
    }
    class TestDataTransfer {
      private stored: File[] = [];
      items = { add: (file: File) => { this.stored.push(file); } };
      get files(): FileList { return this.stored as unknown as FileList; }
    }
    vi.stubGlobal("DataTransfer", TestDataTransfer);
    const payload = makePayload("GREENHOUSE", "Zipline");
    payload.profile.contact.city = "Guadalajara";
    payload.profile.contact.state = "Jalisco";
    payload.profile.contact.country = "Mexico";
    payload.profile.contact.current_location = "Guadalajara, Jalisco, Mexico";
    payload.resume.target_role = "Aerodynamics Intern (Summer 2027)";
    payload.portfolio = { id: 22, version: 1, status: "ready", filename: "Santiago_Example_Project_Portfolio.pdf", target_role: payload.resume.target_role, selected_projects: payload.session.project_experience_json, pdf_url: "/portfolio.pdf" };
    payload.session.portfolio_version_id = 22;
    payload.session.portfolio_filename = payload.portfolio.filename;
    const submitted = vi.fn((event: Event) => event.preventDefault());
    document.getElementById("submit")!.addEventListener("click", submitted);
    const adapter = new GreenhouseAdapter();
    const result = await adapter.fillThisPage(payload, [
      { kind: "RESUME", filename: payload.session.resume_filename, mimeType: "application/pdf", base64: btoa("%PDF-resume"), versionId: payload.session.resume_version_id },
      { kind: "PORTFOLIO", filename: payload.portfolio.filename, mimeType: "application/pdf", base64: btoa("%PDF-portfolio"), versionId: payload.portfolio.id },
    ]);
    const state = adapter.review(payload);

    expect(result.filled).toBeGreaterThanOrEqual(12);
    expect((document.getElementById("country")!.parentElement!.querySelector(".select__single-value") as HTMLElement).textContent).toBe("+52");
    expect((document.getElementById("candidate-location")!.parentElement!.querySelector(".select__single-value") as HTMLElement).textContent).toBe("Guadalajara, Jalisco, Mexico");
    expect((document.getElementById("end-year--0") as HTMLInputElement).value).toBe("2028");
    expect((document.getElementById("source")!.parentElement!.querySelector(".select__single-value") as HTMLElement).textContent).toBe("Google Search");
    expect((document.getElementById("summer")!.parentElement!.querySelector(".select__single-value") as HTMLElement).textContent).toBe("Yes");
    expect((document.getElementById("combined")!.parentElement!.querySelector(".select__single-value") as HTMLElement).textContent).toBe("Yes");
    expect((document.getElementById("authorized") as HTMLInputElement).checked).toBe(false);
    expect((document.getElementById("sponsor") as HTMLInputElement).checked).toBe(true);
    expect((document.getElementById("not-authorized") as HTMLInputElement).checked).toBe(true);
    expect((document.getElementById("resume") as HTMLInputElement).files?.[0]?.name).toBe(payload.session.resume_filename);
    expect((document.getElementById("portfolio") as HTMLInputElement).files?.[0]?.name).toBe(payload.portfolio.filename);
    expect(state.applicationChecks.filter((check) => check.blocking && !check.ready)).toEqual([]);
    expect(state.isReviewPage).toBe(true);
    expect(submitted).not.toHaveBeenCalled();
  });

  it.each([
    ["Intel", "WORKDAY", new WorkdayAdapter(), `<div data-automation-id="formField"><label for="name">Full Name</label><input id="name" /></div>`],
    ["GE Aerospace", "WORKDAY", new WorkdayAdapter(), `<div data-automation-id="formField"><label for="name">Full Name</label><input id="name" /></div>`],
    ["Zipline", "GREENHOUSE", new GreenhouseAdapter(), `<form id="application_form"><label for="name">Full Name</label><input id="name" /></form>`],
    ["Microsoft", "MICROSOFT_CAREERS", new MicrosoftCareersAdapter(), `<form data-testid="application-form"><label for="name">Full Name</label><input id="name" /></form>`],
    ["Amazon / AWS", "AMAZON_JOBS", new AmazonJobsAdapter(), `<form data-test-id="application-form"><label for="name">Full Name</label><input id="name" /></form>`],
    ["Oracle", "ORACLE_CAREERS", new OracleCareersAdapter(), `<div data-oj-binding-provider="none"><label for="name">Full Name</label><input id="name" /></div>`]
  ] as const)("reaches manual READY_FOR_REVIEW for the %s local fixture without submitting", (_company, portal, adapter, fingerprint) => {
    document.body.innerHTML = `${fingerprint}<h1>Review your application</h1><button id="final-action">Submit Application</button>`;
    const state = adapter.review(makePayload(portal, _company));
    expect(state.isReviewPage).toBe(true);
    expect(state.stage).toBe("REVIEW");
    expect(state.supportStatus).not.toBe("PORTAL_CHANGED");
  });

  it("keeps safe autofill paused when the selected portal adapter loses its DOM fingerprint", async () => {
    document.body.innerHTML = `<div data-automation-id="formField"><label for="name">Full Name</label><input id="name" /></div>`;
    const core = new ApplicationAssistantCore(makePayload("WORKDAY", "Intel"));
    document.body.innerHTML = `<form><label for="name">Full Name</label><input id="name" /></form>`;
    expect(core.review().supportStatus).toBe("PORTAL_CHANGED");
    await expect(core.fillThisPage()).rejects.toThrow("portal may have changed");
    expect((document.getElementById("name") as HTMLInputElement).value).toBe("");
  });
});
