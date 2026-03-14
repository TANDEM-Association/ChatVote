"use client";

import { useEffect, useState } from "react";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@components/ui/button";
import { cn } from "@lib/utils";
import { DatabaseIcon } from "lucide-react";

const LOCAL_STORAGE_KEY = "admin_dashboard_secret";
const isDev = process.env.NODE_ENV === "development";

const AdminCoverageLink = () => {
  const router = useRouter();
  const [secret, setSecret] = useState<string | null>(null);

  useEffect(() => {
    if (!isDev) {
      const stored = localStorage.getItem(LOCAL_STORAGE_KEY)?.trim() ?? null;
      if (stored) localStorage.setItem(LOCAL_STORAGE_KEY, stored);
      setSecret(stored);
    }
  }, []);

  // Dev: link to admin dashboard coverage (use env secret or default)
  if (isDev) {
    const devSecret =
      process.env.NEXT_PUBLIC_ADMIN_SECRET ??
      "a2072a50e6375c384b073a3ef8459492560ec1406c69238f98da86c4331d5a79";
    return (
      <Link href={`/admin/dashboard/${devSecret}?tab=coverage`}>
        <Button
          data-sidebar="coverage"
          variant="ghost"
          size="icon"
          className={cn("size-10")}
        >
          <DatabaseIcon />
        </Button>
      </Link>
    );
  }

  // Prod with saved secret: link to admin dashboard
  if (secret) {
    return (
      <Link href={`/admin/dashboard/${secret}?tab=coverage`}>
        <Button
          data-sidebar="coverage"
          variant="ghost"
          size="icon"
          className={cn("size-10")}
        >
          <DatabaseIcon />
        </Button>
      </Link>
    );
  }

  // Prod without secret: prompt for it
  const handleClick = () => {
    const input = window.prompt("Enter admin secret:")?.trim();
    if (input) {
      localStorage.setItem(LOCAL_STORAGE_KEY, input);
      setSecret(input);
      router.push(`/admin/dashboard/${input}?tab=coverage`);
    }
  };

  return (
    <Button
      data-sidebar="coverage"
      variant="ghost"
      size="icon"
      className={cn("size-10")}
      onClick={handleClick}
    >
      <DatabaseIcon />
    </Button>
  );
};

export default AdminCoverageLink;
