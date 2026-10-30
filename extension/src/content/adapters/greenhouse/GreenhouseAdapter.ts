import { SemanticApplicationAdapter } from "../shared/SemanticApplicationAdapter";

export class GreenhouseAdapter extends SemanticApplicationAdapter {
  constructor() {
    super({
      portalType: "GREENHOUSE",
      adapterVersion: "1.1.1",
      supportStatus: "SUPPORTED",
      fieldSelector: "input, textarea, select, [role='combobox']",
      containerSelector: ".field, .field-wrapper, .application-field, [class*='question'], fieldset, [role='group'], .input-wrapper, .select__container, .file-upload",
      optionSelector: "[role='option'], option, [class*='select__option']",
      fingerprintSelectors: [
        "#application_form",
        "#application-form",
        "form.application--form",
        "form[action*='/embed/job_app']",
        "form[action*='greenhouse']",
        "[class*='greenhouse'] form"
      ],
      pageName: "Greenhouse"
    });
  }
}
