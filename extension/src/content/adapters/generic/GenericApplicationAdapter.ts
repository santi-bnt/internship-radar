import { SemanticApplicationAdapter } from "../shared/SemanticApplicationAdapter";

export class GenericApplicationAdapter extends SemanticApplicationAdapter {
  constructor() {
    super({
      portalType: "GENERIC",
      adapterVersion: "1.0.0-beta",
      supportStatus: "BETA",
      fieldSelector: "form input, form textarea, form select, form [role='combobox']",
      containerSelector: ".field, .form-group, [class*='field'], [class*='question'], fieldset, [role='group']",
      optionSelector: "[role='option'], option",
      fingerprintSelectors: [],
      genericSafeOnly: true,
      preserveSavedValues: true,
      pageName: "Generic career portal"
    });
  }
}
