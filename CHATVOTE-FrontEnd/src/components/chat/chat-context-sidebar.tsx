"use client";

import { useCallback, useEffect, useState } from "react";

import {
  type ElectoralList,
  type ElectoralListsByCommune,
} from "@lib/election/election.types";
import { trackElectoralListSelected } from "@lib/firebase/analytics";
import { cn, toTitleCase } from "@lib/utils";
import { CheckCircle2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { useChatStore } from "../providers/chat-store-provider";

type ElectoralListCardProps = {
  list: ElectoralList;
  isSelected?: boolean;
  onSelect: (list: ElectoralList) => void;
};

function ElectoralListCard({
  list,
  isSelected,
  onSelect,
}: ElectoralListCardProps) {
  return (
    <button
      type="button"
      className={cn(
        "relative flex flex-col items-center justify-center gap-1 rounded-lg border p-3 text-center transition-all duration-200",
        "hover:border-primary/50 hover:bg-accent",
        isSelected
          ? "border-primary/40 bg-accent"
          : "border-border-subtle bg-surface",
      )}
      onClick={() => onSelect(list)}
    >
      {isSelected && (
        <CheckCircle2 className="text-primary absolute top-1.5 right-1.5 size-4" />
      )}
      <span className="text-muted-foreground text-xs">
        {list.head_first_name}
      </span>
      <span className="text-sm font-bold">{list.head_last_name}</span>
      {list.nuance_code && <div className="bg-primary/40 mt-0.5 h-px w-8" />}
      <span className="text-muted-foreground text-xs">
        {toTitleCase(list.list_label)}
      </span>
    </button>
  );
}

const ChatContextSidebar = () => {
  const t = useTranslations("chat.sidebar");
  const municipalityCode = useChatStore((s) => s.municipalityCode);
  const selectedElectoralLists = useChatStore((s) => s.selectedElectoralLists);
  const toggleElectoralList = useChatStore((s) => s.toggleElectoralList);
  const setElectoralListsData = useChatStore((s) => s.setElectoralListsData);
  const [data, setData] = useState<ElectoralListsByCommune | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasNoData, setHasNoData] = useState(false);

  useEffect(() => {
    if (!municipalityCode) {
      setData(null);
      setHasNoData(false);
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setHasNoData(false);

    fetch(`/api/electoral-lists?commune_code=${municipalityCode}`, {
      signal: controller.signal,
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
        return res.json() as Promise<ElectoralListsByCommune>;
      })
      .then((result) => {
        if (result === null) return;
        if (!controller.signal.aborted) {
          setData(result);
          setHasNoData(false);
          setElectoralListsData(result.lists);
          setIsLoading(false);
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
  }, [municipalityCode, setElectoralListsData]);

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

  const isOpen = !!municipalityCode;

  return (
    <div
      className={cn(
        "border-border-subtle bg-surface hidden flex-none flex-col overflow-hidden border-r transition-[width] duration-300 ease-in-out md:flex",
        isOpen ? "w-72" : "w-0 border-r-0",
      )}
    >
      <div className="flex h-full w-72 flex-col gap-3 overflow-y-auto p-3">
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground text-xs font-medium uppercase">
            {t("lists")}
          </span>
          {data && (
            <span className="text-muted-foreground text-xs">
              {data.commune_name} · {data.list_count} {t("lists")}
            </span>
          )}
        </div>

        {isLoading && (
          <div className="flex items-center justify-center py-4">
            <div className="border-primary size-5 animate-spin rounded-full border-2 border-t-transparent" />
          </div>
        )}

        {hasNoData && !isLoading && (
          <div className="flex flex-col gap-2 px-2 py-4 text-center">
            <span className="text-muted-foreground text-sm">
              {t("noElectoralData")}
            </span>
            <span className="text-muted-foreground text-xs">
              {t("noElectoralDataHint")}
            </span>
          </div>
        )}

        {data && !isLoading && (
          <div className="grid grid-cols-2 gap-2">
            {data.lists.map((list) => (
              <ElectoralListCard
                key={list.panel_number}
                list={list}
                isSelected={selectedElectoralLists.includes(list.panel_number)}
                onSelect={handleSelectList}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatContextSidebar;
