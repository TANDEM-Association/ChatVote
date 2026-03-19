"use client";

import { type ElectoralList, type ElectoralListsByCommune } from "@lib/election/election.types";
import { cn, toTitleCase } from "@lib/utils";
import { Check } from "lucide-react";
import { useTranslations } from "next-intl";

export type ElectoralListsApiResponse = ElectoralListsByCommune & {
  is_second_round_active?: boolean;
  second_round_party_ids?: string[];
  lists_round_1?: ElectoralList[];
  list_count_round_1?: number;
};

export type FilterMode = "all" | "second-round";

export function ElectoralListCard({
  list,
  isSelected,
  isSecondRound,
  isElected,
  onSelect,
}: {
  list: ElectoralList;
  isSelected?: boolean;
  isSecondRound?: boolean;
  isElected?: boolean;
  onSelect: (list: ElectoralList) => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        "group relative flex w-full items-center gap-2.5 overflow-hidden rounded-lg border py-2.5 pr-3 pl-3 text-left transition-all duration-150",
        "focus-visible:ring-primary/50 focus-visible:outline-none focus-visible:ring-2",
        isSelected
          ? "border-primary/40 bg-primary/5 shadow-sm"
          : isSecondRound
            ? "border-orange-400/25 hover:border-orange-400/50 hover:bg-orange-500/5"
            : "border-border hover:border-border-subtle hover:bg-accent/50",
      )}
      onClick={() => onSelect(list)}
    >
      {/* Corner ribbon */}
      {isElected && (
        <div className="absolute -top-px -right-px z-10">
          <div className="relative size-12">
            <div className="absolute top-0 right-0 h-12 w-12 overflow-hidden">
              <div
                className="absolute top-[6px] -right-[14px] w-[60px] rotate-45 bg-gradient-to-r from-blue-600 via-white to-red-500 py-[2px] text-center text-[7px] font-bold uppercase tracking-wider text-blue-900 shadow-sm"
              >
                Élu
              </div>
            </div>
          </div>
        </div>
      )}
      {isSecondRound && !isElected && (
        <div className="absolute -top-px -right-px z-10">
          <div className="relative size-12">
            <div className="absolute top-0 right-0 h-12 w-12 overflow-hidden">
              <div
                className="absolute top-[6px] -right-[14px] w-[60px] rotate-45 bg-orange-500 py-[2px] text-center text-[7px] font-bold uppercase tracking-wider text-white shadow-sm"
              >
                2nd
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Left accent bar */}
      <div
        className={cn(
          "absolute top-2 bottom-2 left-0 w-[3px] rounded-r-full transition-colors",
          isElected
            ? "bg-gradient-to-b from-blue-600 via-white to-red-500"
            : isSecondRound
              ? "bg-orange-400"
              : "bg-transparent",
        )}
      />

      {/* Selection indicator */}
      <div
        className={cn(
          "flex size-5 shrink-0 items-center justify-center rounded-full border transition-all",
          isSelected
            ? "border-primary bg-primary text-primary-foreground"
            : "border-border bg-background group-hover:border-muted-foreground/40",
        )}
      >
        {isSelected && <Check className="size-3" strokeWidth={3} />}
      </div>

      {/* Content */}
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-foreground text-sm leading-tight font-semibold">
          {list.head_last_name}
        </span>
        <span className="text-muted-foreground text-[11px] leading-tight">
          {list.head_first_name}
        </span>
        <span className="text-muted-foreground/70 mt-0.5 line-clamp-1 text-[10px] leading-snug">
          {toTitleCase(list.list_label)}
        </span>
      </div>
    </button>
  );
}

export function RoundFilterToggle({
  filterMode,
  secondRoundCount,
  totalCount,
  onToggle,
  className,
}: {
  filterMode: FilterMode;
  secondRoundCount: number;
  totalCount: number;
  onToggle: (mode: FilterMode) => void;
  className?: string;
}) {
  const t = useTranslations("chat.sidebar");

  return (
    <div className={cn("bg-muted flex rounded-lg p-0.5", className)}>
      <button
        type="button"
        className={cn(
          "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-all",
          filterMode === "second-round"
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground",
        )}
        onClick={() => onToggle("second-round")}
      >
        {t("round2")}
        <span
          className={cn(
            "inline-flex size-4 items-center justify-center rounded-full text-[9px] font-bold",
            filterMode === "second-round"
              ? "bg-orange-500/15 text-orange-600 dark:text-orange-400"
              : "bg-muted-foreground/10 text-muted-foreground",
          )}
        >
          {secondRoundCount}
        </span>
      </button>
      <button
        type="button"
        className={cn(
          "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-all",
          filterMode === "all"
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground",
        )}
        onClick={() => onToggle("all")}
      >
        {t("round1")}
        <span
          className={cn(
            "inline-flex size-4 items-center justify-center rounded-full text-[9px] font-bold",
            filterMode === "all"
              ? "bg-primary/15 text-primary"
              : "bg-muted-foreground/10 text-muted-foreground",
          )}
        >
          {totalCount}
        </span>
      </button>
    </div>
  );
}

export function ElectoralListCardList({
  sortedLists,
  selectedElectoralLists,
  hasSecondRound,
  secondRoundPanelNumbers,
  onSelect,
}: {
  sortedLists: ElectoralList[];
  selectedElectoralLists: number[];
  hasSecondRound: boolean;
  secondRoundPanelNumbers: Set<number>;
  onSelect: (list: ElectoralList) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      {sortedLists.map((list, idx) => {
        const isInSecondRound =
          hasSecondRound && secondRoundPanelNumbers.has(list.panel_number);
        const isElected =
          isInSecondRound && secondRoundPanelNumbers.size === 1;
        const prevIsSecondRound =
          idx > 0 &&
          hasSecondRound &&
          secondRoundPanelNumbers.has(sortedLists[idx - 1].panel_number);
        const showDivider =
          hasSecondRound && idx > 0 && !isInSecondRound && prevIsSecondRound;

        return (
          <div key={list.panel_number}>
            {showDivider && (
              <div className="border-border my-1.5 border-t" />
            )}
            <ElectoralListCard
              list={list}
              isSelected={selectedElectoralLists.includes(list.panel_number)}
              isSecondRound={isInSecondRound}
              isElected={isElected}
              onSelect={onSelect}
            />
          </div>
        );
      })}
    </div>
  );
}

/** Sort lists with second-round candidates first */
export function sortListsByRound(
  lists: ElectoralList[],
  hasSecondRound: boolean,
  secondRoundPanelNumbers: Set<number>,
): ElectoralList[] {
  if (!hasSecondRound) return lists;
  return [...lists].sort((a, b) => {
    const aIs2nd = secondRoundPanelNumbers.has(a.panel_number) ? 0 : 1;
    const bIs2nd = secondRoundPanelNumbers.has(b.panel_number) ? 0 : 1;
    return aIs2nd - bIs2nd;
  });
}
