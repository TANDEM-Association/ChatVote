"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@lib/utils";

export type NavbarItemDetails = {
  label: string;
  href: string;
  highlight?: boolean;
  external?: boolean;
  icon?: React.ReactNode;
};

type NavbarItemProps = {
  details: NavbarItemDetails;
  onClose?: () => void;
};

export const NavbarItem: React.FC<NavbarItemProps> = ({ details, onClose }) => {
  const { label, href, external, highlight } = details;
  const pathname = usePathname();
  const isActive = href === "/" ? pathname === href : pathname.startsWith(href);

  return (
    <Link
      href={href}
      target={external ? "_blank" : undefined}
      className={cn(
        "relative flex items-center gap-1 rounded-md p-3 text-sm",
        isActive
          ? "text-primary font-medium"
          : "text-primary/50 hover:text-primary/70",
        highlight &&
          "border-none text-indigo-900 hover:text-indigo-900 dark:text-indigo-100 dark:hover:text-indigo-50",
      )}
      onClick={onClose}
    >
      {highlight && (
        <span className="relative mr-1 flex size-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-600 opacity-75" />
          <span className="relative inline-flex size-2 rounded-full bg-indigo-600" />
        </span>
      )}
      <span className="relative z-50">{label}</span>
      {isActive && !highlight && (
        <span className="bg-muted absolute inset-0 rounded-md" />
      )}

      {highlight && (
        <span className="absolute inset-0 rounded-md border border-indigo-600 bg-indigo-600/20 transition-colors hover:bg-indigo-600/30" />
      )}
    </Link>
  );
};
