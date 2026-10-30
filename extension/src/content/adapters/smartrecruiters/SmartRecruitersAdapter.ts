import { SemanticApplicationAdapter } from "../shared/SemanticApplicationAdapter";

export class SmartRecruitersAdapter extends SemanticApplicationAdapter {
  constructor() {
    super({
      portalType: "SMARTRECRUITERS",
      adapterVersion: "1.0.0-beta",
      supportStatus: "BETA",
      fieldSelector: "form input, form textarea, form select, form [role='combobox']",
      containerSelector: "[data-test*='field'], [class*='field'], [class*='question'], fieldset, [role='group']",
      optionSelector: "[role='option'], option, [data-test*='option']",
      fingerprintSelectors: ["form[action*='smartrecruiters'], [data-test*='application'], [class*='smartrecruiters']"],
      preserveSavedValues: true,
      structuredSkills: true,
      structuredLanguages: true,
      pageName: "SmartRecruiters",
    });
  }
}
