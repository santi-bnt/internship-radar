"use client";

import {
  BriefcaseBusiness,
  Building2,
  LayoutDashboard,
  Radar,
  RefreshCw,
  Settings,
  ShieldCheck,
  Send,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { switchGoogleAccount } from "@/app/auth-actions";

const links = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { href: "/applications", label: "Applications", icon: Send },
  { href: "/profile", label: "Profile", icon: UserRound },
  { href: "/sources", label: "Sources", icon: Building2 },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/account", label: "Account", icon: ShieldCheck },
];

export function Navigation() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="Internship Radar dashboard">
        <span className="brand-mark"><Radar size={21} /></span>
        <span>
          <strong>Internship Radar</strong>
          <small>Candidate workspace</small>
        </span>
      </Link>
      <nav aria-label="Primary navigation">
        {links.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link key={href} href={href} className={active ? "nav-link active" : "nav-link"}>
              <Icon size={18} />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-foot">
        <span className="workspace-status">
          <span className="live-dot" />
          Private workspace
        </span>
        <form action={switchGoogleAccount}>
          <button className="sidebar-switch-account" type="submit">
            <RefreshCw size={14} />
            Switch Google account
          </button>
        </form>
      </div>
    </aside>
  );
}
