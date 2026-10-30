import { SemanticApplicationAdapter } from "../shared/SemanticApplicationAdapter";

export class AmazonJobsAdapter extends SemanticApplicationAdapter {
  constructor() {
    super({
      portalType: "AMAZON_JOBS",
      adapterVersion: "1.0.0-beta",
      supportStatus: "BETA",
      fieldSelector: "input, textarea, select, [role='combobox']",
      containerSelector: "[data-test-id*='field'], [data-testid*='field'], .form-group, fieldset, [role='group']",
      optionSelector: "[role='option'], option, [data-test-id*='option'], [data-testid*='option']",
      fingerprintSelectors: ["[data-test-id*='application']", "[data-testid*='application']", "form[action*='amazon.jobs']"],
      preserveSavedValues: true,
      pageName: "Amazon Jobs"
    });
  }
}
