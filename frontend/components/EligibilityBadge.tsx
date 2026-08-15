import { AlertTriangle, BadgeCheck, CircleHelp, CircleSlash2, ShieldCheck } from "lucide-react";

import type { EligibilityState } from "@/lib/types";

export const eligibilityLabels: Record<EligibilityState, string> = {
  ELIGIBLE: "Eligible",
  LIKELY_ELIGIBLE: "Likely eligible",
  UNKNOWN: "Eligibility unclear",
  LIKELY_INELIGIBLE: "Likely ineligible",
  NOT_ELIGIBLE: "Not eligible",
};

const config = {
  ELIGIBLE: { className: "badge green", icon: ShieldCheck },
  LIKELY_ELIGIBLE: { className: "badge blue", icon: BadgeCheck },
  UNKNOWN: { className: "badge violet", icon: CircleHelp },
  LIKELY_INELIGIBLE: { className: "badge amber", icon: AlertTriangle },
  NOT_ELIGIBLE: { className: "badge red", icon: CircleSlash2 },
};

export function EligibilityBadge({ value }: { value: EligibilityState }) {
  const item = config[value] ?? config.UNKNOWN;
  const Icon = item.icon;
  return <span className={item.className}><Icon size={13} />{eligibilityLabels[value] ?? eligibilityLabels.UNKNOWN}</span>;
}
