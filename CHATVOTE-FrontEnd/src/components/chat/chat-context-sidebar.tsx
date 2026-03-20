"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { type ElectoralList } from "@lib/election/election.types";
import { trackElectoralListSelected } from "@lib/firebase/analytics";
import { cn } from "@lib/utils";
import { useTranslations } from "next-intl";

import {
  type ElectoralListsApiResponse,
  type FilterMode,
  ElectoralListCardList,
  RoundFilterToggle,
  sortListsByRound,
} from "./electoral-list-shared";
import { useChatStore } from "../providers/chat-store-provider";

const ChatContextSidebar = () => {
  const t = useTranslations("chat.sidebar");
  const municipalityCode = useChatStore((s) => s.municipalityCode);
  const selectedElectoralLists = useChatStore((s) => s.selectedElectoralLists);
  const toggleElectoralList = useChatStore((s) => s.toggleElectoralList);
  const setElectoralListsData = useChatStore((s) => s.setElectoralListsData);
  const setSecondRoundPartyIds = useChatStore(
    (s) => s.setSecondRoundPartyIds,
  );
  const setSelectedElectoralLists = useChatStore(
    (s) => s.setSelectedElectoralLists,
  );
  const [data, setData] = useState<ElectoralListsApiResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasNoData, setHasNoData] = useState(false);
  const [filterMode, setFilterMode] = useState<FilterMode>("second-round");

  useEffect(() => {
    if (!municipalityCode) {
      setData(null);
      setHasNoData(false);
      setSecondRoundPartyIds(null);
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setHasNoData(false);

    fetch(`/api/electoral-lists?commune_code=${municipalityCode}`, {
      signal: controller.signal,
      cache: "no-store",
    })
      .then((res) => {
        if (!res.ok) {
          if (res.status === 404) {
            if (!controller.signal.aborted) {
              setHasNoData(true);
              setIsLoading(false);
            }
            return null;
          }
          throw new Error("Failed to fetch");
        }
        return res.json() as Promise<ElectoralListsApiResponse>;
      })
      .then((result) => {
        if (result === null) return;
        if (!controller.signal.aborted) {
          setData(result);
          setHasNoData(false);
          setElectoralListsData(result.lists);
          setIsLoading(false);
          if (result.second_round_party_ids?.length) {
            setSecondRoundPartyIds(result.second_round_party_ids);
          } else {
            setSecondRoundPartyIds(null);
          }
          if (result.is_second_round_active && result.lists?.length) {
            setFilterMode("second-round");
            setSelectedElectoralLists(
              result.lists.map((l) => l.panel_number),
            );
          } else {
            setFilterMode("all");
          }
        }
      })
      .catch((err) => {
        if (err instanceof Error && err.name === "AbortError") return;
        console.error("Failed to fetch electoral lists:", err);
        if (!controller.signal.aborted) {
          setHasNoData(true);
          setIsLoading(false);
        }
      });

    return () => controller.abort();
  }, [municipalityCode, setElectoralListsData, setSecondRoundPartyIds]);

  const handleSelectList = useCallback(
    (list: ElectoralList) => {
      toggleElectoralList(list.panel_number);
      trackElectoralListSelected({
        panel_number: list.panel_number,
        list_label: list.list_label,
      });
    },
    [toggleElectoralList],
  );

  const hasSecondRound = !!data?.is_second_round_active;
  const isFirstRoundDecided = !!data?.is_first_round_decided;
  const firstRoundElectedPanel = data?.first_round_elected?.panel_number;
  const secondRoundPanelNumbers = useMemo(
    () => new Set(data?.lists?.map((l) => l.panel_number) ?? []),
    [data?.lists],
  );
  const allLists = data?.lists_round_1 ?? data?.lists ?? [];
  const totalCount = data?.list_count_round_1 ?? data?.list_count ?? 0;
  const secondRoundCount = secondRoundPanelNumbers.size;

  const sortedLists = useMemo(
    () => sortListsByRound(allLists, hasSecondRound, secondRoundPanelNumbers),
    [allLists, hasSecondRound, secondRoundPanelNumbers],
  );

  const handleToggleFilter = useCallback(
    (mode: FilterMode) => {
      setFilterMode(mode);
      if (mode === "second-round" && data?.lists?.length) {
        setSelectedElectoralLists(
          data.lists.map((l) => l.panel_number),
        );
      } else {
        setSelectedElectoralLists(
          allLists.map((l) => l.panel_number),
        );
      }
    },
    [data, allLists, setSelectedElectoralLists],
  );

  const isOpen = !!municipalityCode;

  return (
    <div
      className={cn(
        "border-border bg-background hidden flex-none flex-col overflow-hidden border-r transition-[width] duration-300 ease-in-out md:flex",
        isOpen ? "w-56 lg:w-72" : "w-0 border-r-0",
      )}
    >
      <div className="flex h-full w-56 flex-col overflow-y-auto lg:w-72">
        {/* Header */}
        <div className="border-border sticky top-0 z-10 border-b bg-inherit px-3 pt-3 pb-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-foreground text-xs font-semibold uppercase tracking-wider">
              {t("lists")}
            </h2>
            {data && (
              <span className="text-muted-foreground truncate text-[10px]">
                {data.commune_name}
              </span>
            )}
          </div>

          {hasSecondRound && !isLoading && (
            <RoundFilterToggle
              filterMode={filterMode}
              secondRoundCount={secondRoundCount}
              totalCount={totalCount}
              onToggle={handleToggleFilter}
              className="mt-2"
            />
          )}
        </div>

        {/* List content */}
        <div className="flex-1 px-2 py-2">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <div className="border-primary size-5 animate-spin rounded-full border-2 border-t-transparent" />
            </div>
          )}

          {hasNoData && !isLoading && (
            <div className="flex flex-col gap-2 px-2 py-6 text-center">
              <span className="text-muted-foreground text-sm">
                {t("noElectoralData")}
              </span>
              <span className="text-muted-foreground/60 text-xs">
                {t("noElectoralDataHint")}
              </span>
            </div>
          )}

          {data && !isLoading && (
            <ElectoralListCardList
              sortedLists={sortedLists}
              selectedElectoralLists={selectedElectoralLists}
              hasSecondRound={hasSecondRound}
              secondRoundPanelNumbers={secondRoundPanelNumbers}
              firstRoundElectedPanel={isFirstRoundDecided ? firstRoundElectedPanel : undefined}
              onSelect={handleSelectList}
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatContextSidebar;
