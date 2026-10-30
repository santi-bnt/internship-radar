import { SemanticApplicationAdapter } from "../shared/SemanticApplicationAdapter";

export class MicrosoftCareersAdapter extends SemanticApplicationAdapter {
  constructor() {
    super({
      portalType: "MICROSOFT_CAREERS",
      adapterVersion: "1.0.0-beta",
      supportStatus: "BETA",
      fieldSelector: "input, textarea, select, [role='combobox']",
      containerSelector: "[data-testid*='field'], [data-automation-id*='field'], .field, fieldset, [role='group']",
      optionSelector: "[role='option'], option, [data-testid*='option']",
      fingerprintSelectors: ["[data-testid*='application']", "[data-automation-id*='microsoft']", "form[action*='careers.microsoft']"],
      preserveSavedValues: true,
      structuredSkills: true,
      pageName: "Microsoft Careers"
    });
  }
}
