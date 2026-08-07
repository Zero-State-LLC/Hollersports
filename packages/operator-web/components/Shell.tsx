"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { ComplianceGate } from "@/components/ComplianceGate";

const NAV = [
  { href: "/", label: "Today" },
  { href: "/book", label: "Paper book" },
  { href: "/health", label: "Health" },
] as const;

export type ShellProps = {
  children: ReactNode;
  runId?: string;
};

export function Shell({ children, runId }: ShellProps) {
  const pathname = usePathname() || "/";

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  const colophon = [
    "ADVISORY_ONLY",
    "no real money",
    "PAPER_SIM",
    "not a sportsbook",
    "capital_authority=false",
    "18+/21+ where required",
    "schema v1",
    "api :8000",
    runId ? `run_id=${runId}` : "run_id=—",
  ].join(" · ");

  return (
    <ComplianceGate>
      <div className="shell">
        <aside className="shell-rail" aria-label="Primary">
          <div className="shell-brand">
            HollerSports
            <span className="shell-brand-sub">advise · never fund</span>
          </div>
          <nav className="shell-nav" aria-label="Workbench">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive(item.href) ? "page" : undefined}
                title={
                  item.href === "/book"
                    ? "Paper ticket book — simulation only, not a sportsbook"
                    : undefined
                }
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="shell-main">{children}</main>
        <footer className="shell-colophon" aria-label="Colophon">
          {colophon}
        </footer>
      </div>
    </ComplianceGate>
  );
}
