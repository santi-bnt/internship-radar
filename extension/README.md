# Internship Radar Multi-Portal Apply Assistant

Private Manifest V3 extension for user-controlled application assistance. Version 2.4 uses one verified Application Profile, one job-specific Recommended Resume, and the exact role-specific experience/skill snapshot reviewed before its Application Session was created. Runtime URL and DOM evidence select the portal adapter; optional local vision is a fallback for controls without reliable DOM semantics.

## Job-specific CV and question help

Opening **Apply with Assistant** in the jobs workspace requests a new CV through the normal resume generation queue and waits for compilation and validation. The new version is bound explicitly to the application; existing compiled CVs are not selected as a fallback. Closing the preparation dialog stops polling while queued generation continues.

On the application portal, choose **Read questions & draft answers** to inspect the current form without changing its fields. The panel displays supported open-ended questions together, with editable drafts, evidence references, character limits, **Copy answer**, and **Use reviewed answer**. Suggestions use verified projects and skills, with the question's subject taking precedence over general job overlap. Questions without supported evidence remain available for manual completion. Drafts stay local to the application session and page; edits survive panel polling and are cleared when the connected session or page changes.

Use **Analyze & Fill Safely** or **Run Safe Autopilot** for the existing assisted filling flow. Authentication, assessments and final submission keep their existing manual handling. After rebuilding, reload the extension from the browser's extensions page to load these controls.

## Portal support

| Target | Adapter | Production status |
| --- | --- | --- |
| Intel | `WorkdayAdapter` + Intel policy | Supported by local fixture through Review |
| GE Aerospace | `WorkdayAdapter` + GE policy | Supported by local fixture through Review |
| Zipline | `GreenhouseAdapter` | Supported by a current-form regression dry run through Review |
| Microsoft | `MicrosoftCareersAdapter` | Beta |
| Amazon / AWS | `AmazonJobsAdapter` | Beta |
| Oracle | `OracleCareersAdapter` | Beta |
| Unknown HTTPS portal | `GenericApplicationAdapter` | Beta, basic safe fields only |
| SmartRecruiters | `SmartRecruitersAdapter` | Beta |
| Lever, Ashby, Google Careers | Detection only | Unsupported |

`SUPPORTED` means the local representative fixture reaches `READY_FOR_REVIEW` without activating final submission. It does not promise that a third-party portal will never change. Adapter diagnostics change the status to `PORTAL_CHANGED` and pause autofill when expected fingerprints disappear.

## Safety boundary

The assistant may fill verified contact, education, links, job-ranked skills, role-specific projects, the CV bound to the session, and exact recognized legal/availability answers previously confirmed in the canonical profile. Those review-required answers are always shown together before final submission. It never:

- enters or stores a career-site password;
- reads or answers MFA, CAPTCHA, security challenges, electronic signatures, coding tests, behavioral assessments, or online assessments;
- guesses new or ambiguous legal, citizenship, work-authorization, sponsorship, government, disability, veteran, conflict, IP, or relocation answers;
- invents employment, skills, projects, dates, or qualifications;
- replaces the CV version bound to the Application Session;
- activates a final `Submit`, `Apply`, `Complete Application`, `Certify and Submit`, or `Send Application` action.

Final-submit blocking exists in the UI, every adapter, and `ApplicationAssistantCore`.

## Permission model

The extension has permanent host access only to the Internship Radar web bridge. Career-site access is optional. When the user opens the side panel and selects **Enable Apply Assistant Here**, Chrome requests permission for that exact HTTPS origin and injects `assistant.js`. Unrelated sites are not monitored.

The extension receives only a short-lived, scoped, revocable Application Session token. It contains no `INTERNAL_API_SECRET`, Google secret, SMTP credential, API key, or career-site credential.

## Build and install

```powershell
Set-Location .\extension
npm install
npm run lint
npm run typecheck
npm test
npm run build
```

Load `extension/dist` as an unpacked extension:

1. Chrome: open `chrome://extensions`; Edge: `edge://extensions`; Opera: `opera://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose `extension/dist`.
5. Pin **Internship Radar Apply Assistant**.

After rebuilding, select **Reload** on the extension card.

For optional on-device vision, install Ollama, run `ollama pull gemma3:4b`, and leave the Ollama service running. **Run Safe Autopilot** fills and advances up to six safe sections. It uses a redacted active-tab screenshot only when DOM/accessibility interpretation leaves a blocking control. The screenshot and model response stay local and are not persisted. Safe Autopilot stops before review, sensitive questions, assessments, CAPTCHA, signatures, and final submission.

Internship Radar checks that the matching extension version is active before it creates an Application Session or opens a career portal. If the readiness dialog reports that the extension is missing, reload the unpacked extension, refresh Internship Radar, and select **Check again**. A missing extension never opens a blank application tab.

Chrome and Edge use the native side panel. Browsers without `chrome.sidePanel`, including Opera versions that omit that API, open the same Apply Assistant controls in an extension tab when you click the extension icon from the career application page.

## Exact non-submitting tests

For every test, use a real application only if you intend to apply. Stop at Review, never press the final portal button during an adapter test, and record fields as `AUTO_FILLED`, `USER_CONFIRMED`, `MANUAL`, `FAILED`, or `UNKNOWN`.

### Intel

1. Open an eligible Intel role whose application redirects to Workday.
2. Start **Apply with Assistant**, open the side panel, and grant that Workday origin.
3. Confirm contact, education, languages, job-ranked skills, websites, and the session CV.
4. Verify former-Intel, authorization, sponsorship, IP, secondary-employment, citizenship, and compliance questions require explicit confirmation.
5. Reach Review and confirm **Continue** is disabled. Stop before Submit.

### GE Aerospace

1. Start an eligible GE Aerospace Workday application and enable its exact origin.
2. Verify address, education, links, skills, project experience, and CV.
3. Confirm government-employment, family-government, confidentiality, authorization, and voluntary-disclosure questions are never silently selected.
4. Reach Review and stop before Submit.

### Zipline

1. Open the canonical Zipline role and follow its actual Greenhouse-backed application flow.
2. Enable the final Greenhouse or Zipline form origin shown in the address bar.
3. Verify name, email, phone, current location, LinkedIn, school, expected graduation, and role-specific project text.
4. Verify the exact session CV and optional job-specific portfolio PDF are attached, or use the prepared-file controls if the browser blocks direct assignment.
5. Verify the Google-search source and both previously confirmed seasonal-availability answers.
6. For a U.S. job, verify U.S. authorization is No and sponsorship is Yes; for a Mexico job, verify authorization is Yes and sponsorship is No.
7. Review the complete **Legal & Eligibility Answers** and **Application Check** sections. Reach Review and stop before Submit.

### Microsoft

1. Start a Microsoft application and enable the Microsoft Careers origin.
2. If Microsoft already saved profile data, verify conflicts show both the portal and verified value.
3. Test **Keep portal value** and **Use verified value** on a noncritical fixture or field.
4. Verify authorization, sponsorship, relocation, and job questions require confirmation/review.
5. Treat the adapter as Beta and stop at Review.

### Amazon / AWS

1. Start an Amazon Jobs student/internship application and enable its exact origin.
2. Verify contact, education, student status, graduation, availability, location, and CV assistance.
3. Navigate only until an online/coding/behavioral assessment is detected.
4. Confirm autofill pauses and displays **Continue Manually**. The assistant must not answer any assessment.
5. If no assessment occurs, stop at Review.

### Oracle

1. Start an eligible Oracle role; restricted veteran/special programs should remain blocked unless explicitly overridden in Internship Radar.
2. Enable the actual Oracle or redirected ATS origin.
3. Verify contact, education, skills, languages, student/graduation data, and CV.
4. Confirm authorization, sponsorship, and custom legal questions require user action.
5. If expected Oracle fingerprints are absent, verify `PORTAL_CHANGED` pauses autofill; continue manually. Otherwise stop at Review.

## Automatic continue and manual fallback

**Automatically continue safe pages** is off by default. It runs only after the user selects **Fill This Page**, when no sensitive answer, assessment, inconsistency stop, portal-change stop, or Review page is present. **Continue Manually** is always available.

## Developer diagnostics

Enable extension-local diagnostics from the extension service-worker developer tools:

```js
chrome.storage.local.set({ developerDebugEnabled: true })
```

The side panel then displays adapter version, detection evidence, confidence, detected/filled/failed/unknown counts, normalized field key, policy, and saved-profile conflict classification. It never displays password, MFA, CAPTCHA, or arbitrary unrelated-site values.
