"use client";

import { usePathname } from "next/navigation";

import { Navigation } from "@/components/Navigation";

const standalonePaths = ["/login", "/maintenance", "/access-denied"];

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const standalone = standalonePaths.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );

  return (
    <div className={standalone ? "app-shell standalone-shell" : "app-shell"}>
      {!standalone && <Navigation />}
      <main className={standalone ? "page standalone-page" : "page"}>{children}</main>
    </div>
  );
}
