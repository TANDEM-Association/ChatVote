"use client";

import { Badge } from "@components/ui/badge";
import { cn } from "@lib/utils";

const FIABILITE_CONFIG: Record<number, { label: string; color: string }> = {
  1: { label: "Government", color: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200" },
  2: { label: "Official", color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" },
  3: { label: "Press", color: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200" },
  4: { label: "Social Media", color: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" },
};

export function FiabiliteBadge({ level }: { level?: number }) {
  if (!level) return null;
  const config = FIABILITE_CONFIG[level];
  if (!config) return null;
  return (
    <Badge variant="outline" className={cn("text-[10px]", config.color)}>
      {config.label} ({level})
    </Badge>
  );
}

export function ThemeBadge({ theme }: { theme?: string }) {
  if (!theme) return null;
  return (
    <Badge variant="secondary" className="text-[10px]">
      {theme}
    </Badge>
  );
}

export function SourceDocBadge({ sourceDoc }: { sourceDoc?: string }) {
  if (!sourceDoc) return null;
  return (
    <Badge variant="outline" className="text-[10px]">
      {sourceDoc}
    </Badge>
  );
}

export function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 0.8
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200"
      : score >= 0.6
        ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
        : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
  return (
    <Badge variant="outline" className={cn("font-mono text-[10px]", color)}>
      {score.toFixed(3)}
    </Badge>
  );
}
