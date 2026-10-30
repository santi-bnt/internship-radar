import { AlertTriangle, CheckCircle2, CircleSlash2, Clock3, SearchCheck, XCircle } from "lucide-react";

import type { Recommendation } from "@/lib/types";

const statusConfig = {
  "Apply Now": { className: "badge green", icon: CheckCircle2 },
  "Apply Today": { className: "badge green", icon: CheckCircle2 },
  Review: { className: "badge amber", icon: AlertTriangle },
  "Needs Verification": { className: "badge violet", icon: SearchCheck },
  "Not Eligible": { className: "badge red", icon: CircleSlash2 },
  "Low Match": { className: "badge blue", icon: Clock3 },
  Closed: { className: "badge gray", icon: XCircle },
  Expired: { className: "badge gray", icon: XCircle },
};

export function StatusBadge({ value }: { value: Recommendation | string }) {
  const config = statusConfig[value as Recommendation] ?? statusConfig.Closed;
  const Icon = config.icon;
  return (
    <span className={config.className}>
      <Icon size={13} />
      {value}
    </span>
  );
}
