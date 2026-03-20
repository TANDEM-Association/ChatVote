"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { type ElectoralList } from "@lib/election/election.types";
import { trackElectoralListSelected } from "@lib/firebase/analytics";
import { useTranslations } from "next-intl";

import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from "@components/ui/drawer";
import { useChatStore } from "../../providers/chat-store-provider";
import {
  type ElectoralListsApiResponse,
  type FilterMode,
  ElectoralListCardList,
  RoundFilterToggle,
  sortListsByRound,
} from "../electoral-list-shared";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

const ElectoralListsDrawer = ({ open, onOpenChange }: Props) => {
  const t = useTranslations("chat.sidebar");
  const municipalityCode = useChatStore((s) => s.municipalityCode);
  const selectedElectoralLists = useChatStore((s) => s.selectedElectoralLists);
  const toggleElectoralList = useChatStore((s) => s.toggleElectoralList);
  const setSelectedElectoralLists = useChatStore(
    (s) => s.setSelectedElectoralLists,
  );
  const setSecondRoundPartyIds = useChatStore(
    (s) => s.setSecondRoundPartyIds,
  );
  const [data, setData] = useState<ElectoralListsApiResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [filterMode, setFilterMode] = useState<FilterMode>("second-round");

  useEffect(() => {
    if (!municipalityCode) {
      setData(null);
      setSecondRoundPartyIds(null);
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);

    fetch(`/api/electoral-lists?commune_code=${municipalityCode}`, {
      signal: controller.signal,
      cache: "no-store",
    })
      .then((res) => {
        if (!res.ok) return null;
        return res.json() as Promise<ElectoralListsApiResponse>;
      })
      .then((result) => {
        if (result === null || controller.signal.aborted) return;
        setData(result);
        setIsLoading(false);
        if (result.second_round_party_ids?.length) {
          setSecondRoundPartyIds(result.second_round_party_ids);
        }
        if (result.is_second_round_active && result.lists?.length) {
          setFilterMode("second-round");
          setSelectedElectoralLists(
            result.lists.map((l) => l.panel_number),
          );
        } else {
          setFilterMode("all");
        }
      })
      .catch((err) => {
        if (err instanceof Error && err.name === "AbortError") return;
        setIsLoading(false);
      });

    return () => controller.abort();
  }, [municipalityCode, setSecondRoundPartyIds, setSelectedElectoralLists]);

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
        setSelectedElectoralLists(data.lists.map((l) => l.panel_number));
      } else {
        setSelectedElectoralLists(allLists.map((l) => l.panel_number));
      }
    },
    [data, allLists, setSelectedElectoralLists],
  );

  if (!municipalityCode || !data) return null;

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-h-[85vh]">
        <DrawerHeader className="pb-2">
          <DrawerTitle className="flex items-baseline justify-between">
            <span>{t("lists")}</span>
            <span className="text-muted-foreground text-xs font-normal">
              {data.commune_name} · {totalCount}
            </span>
          </DrawerTitle>

          {hasSecondRound && !isLoading && (
            <RoundFilterToggle
              filterMode={filterMode}
              secondRoundCount={secondRoundCount}
              totalCount={totalCount}
              onToggle={handleToggleFilter}
              className="mt-1"
            />
          )}
        </DrawerHeader>

        <div className="overflow-y-auto px-4 pb-6">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <div className="border-primary size-5 animate-spin rounded-full border-2 border-t-transparent" />
            </div>
          )}

          {!isLoading && (
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
      </DrawerContent>
    </Drawer>
  );
};

export default ElectoralListsDrawer;
