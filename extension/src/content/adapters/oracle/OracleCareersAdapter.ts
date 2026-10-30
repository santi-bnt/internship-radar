import { SemanticApplicationAdapter } from "../shared/SemanticApplicationAdapter";

export class OracleCareersAdapter extends SemanticApplicationAdapter {
  constructor() {
    super({
      portalType: "ORACLE_CAREERS",
      adapterVersion: "1.0.0-beta",
      supportStatus: "BETA",
      fieldSelector: "input, textarea, select, [role='combobox'], oj-input-text input, oj-select-single input",
      containerSelector: "oj-form-layout, [class*='form-field'], [class*='question'], fieldset, [role='group']",
      optionSelector: "[role='option'], option, oj-option, [class*='oj-listbox-result']",
      fingerprintSelectors: ["[data-oj-binding-provider]", "oj-input-text", "[class*='candidate-experience']", "form[action*='oraclecloud']"],
      preserveSavedValues: true,
      structuredSkills: true,
      structuredLanguages: true,
      pageName: "Oracle Careers"
    });
  }
}
