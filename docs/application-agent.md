# Local-first AI Application Agent

Internship Radar's application agent sits above the portal adapters. It reads DOM and accessibility-derived field descriptors, resolves them against the authenticated user's application profile, and returns validated structured decisions. The extension remains the deterministic executor and never accepts arbitrary JavaScript or coordinate-click instructions.

## Processing modes

- `LOCAL_ONLY`: local provider only; an unavailable local model never triggers an external request.
- `BALANCED`: deterministic and local processing first, with a privacy-filtered external fallback available to provider-routed tasks.
- `EXTERNAL_ALLOWED`: allows non-sensitive external reasoning after the same mandatory minimization and redaction policy.

The provider abstraction currently includes an Ollama-compatible local provider and an OpenAI structured-output provider. Ordinary profile fields, authorization facts, degree matching, and the current evidence-based answer templates use deterministic local logic and do not require either provider.

## Privacy boundary

`CandidateAIContextBuilder` produces an identity-free evidence context shared by resume tailoring and the application agent. The external privacy filter removes personal contact details, work-authorization data, sensitive disclosures, authentication data, government identifiers, financial data, medical data, and electronic signatures. It also redacts identifiers embedded in free text.

Every external provider call made through `AIRouter` supports an audit callback with the purpose, included field paths, and redacted field paths. It never records API secrets or hidden reasoning. Application decision logs store concise explanations and redact selected personal or sensitive values.

## Decision and execution safety

Question categories map to one of `AUTO_FILL`, `AUTO_FILL_REVIEW`, `GENERATE_REVIEW`, `CONFIRM`, or `MANUAL_ONLY`. Confidence below 0.80 cannot be executed automatically. Dropdown options must exist in the live field descriptor. Disability and other voluntary disclosures, assessments, attestations, passwords, MFA, CAPTCHA, and final submission stay manual regardless of confidence.

Degree mappings preserve the canonical profile value. If Robotics is absent, programming-oriented truthful options are preferred before unrelated engineering options. Related programming mappings require review and can be saved per user and portal after explicit approval.

Corrections are owner-scoped and may be stored globally for one user or limited to a portal, company, question alias, or application. No profile, correction, legal answer, resume, project, or decision falls back to another user.

## Browser extension

Version 2.4.0 adds **Safe Autopilot**. It can fill and advance several safe application sections, recover from temporary API failures, and optionally use a local Ollama vision model to label controls that are inaccessible through normal DOM semantics. Screenshots are redacted in extension memory, sent only to `127.0.0.1`, never persisted, and never routed to an external model. Visual actions are revalidated against live DOM controls. Submit/Apply, CAPTCHA, passwords, MFA, assessments, attestations, signatures, and sensitive voluntary disclosures remain manual. Workday and Greenhouse remain supported; Microsoft, Amazon, Oracle, SmartRecruiters, and generic forms use beta adapters.

The user always performs the final review and manually presses Submit.

### Local vision setup

Safe Autopilot works without a model and invokes vision only when normal DOM/accessibility filling leaves blocking controls. For the optional local fallback, install Ollama and pull a supported vision model such as `gemma3:4b`. The extension asks for access only to `http://127.0.0.1:11434` when Safe Autopilot is started. Keep the application tab visible during a visual pass because only the active viewport is captured.
