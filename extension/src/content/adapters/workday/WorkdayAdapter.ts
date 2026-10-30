import { SemanticApplicationAdapter } from "../shared/SemanticApplicationAdapter";

export class WorkdayAdapter extends SemanticApplicationAdapter {
  constructor() {
    super({
      portalType: "WORKDAY",
      adapterVersion: "2.0.0",
      supportStatus: "SUPPORTED",
      fieldSelector: "input, textarea, select, [role='combobox']",
      containerSelector: "[data-automation-id*='formField'], [data-automation-id*='question'], fieldset, [role='group']",
      optionSelector: "[role='option'], li[data-automation-id], [data-automation-id*='promptOption']",
      fingerprintSelectors: ["[data-automation-id*='formField']", "[data-automation-id*='jobPosting']", "[data-uxi-widget-type]"],
      structuredSkills: true,
      structuredLanguages: true,
      pageName: "Workday"
    });
  }
}
