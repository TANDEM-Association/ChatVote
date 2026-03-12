"use client";

import { useCallback, useEffect, useState } from "react";

import {
  type ElectoralList,
  type ElectoralListsByCommune,
} from "@lib/election/election.types";
import { cn, toTitleCase } from "@lib/utils";
import { CheckCircle2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { useChatStore } from "../../providers/chat-store-provider";

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
        <CheckCircle2 className="absolute top-1.5 right-1.5 size-4 text-primary" />
      )}
      <span className="text-xs text-muted-foreground">
        {list.head_first_name}
      </span>
      <span className="text-sm font-bold">
        {list.head_last_name}
      </span>
      {list.nuance_code && (
        <div className="mt-0.5 h-px w-8 bg-primary/40" />
      )}
      <span className="text-xs text-muted-foreground">
        {toTitleCase(list.list_label)}
      </span>
    </button>
  );
}

const SidebarElectoralLists = () => {
  const t = useTranslations("chat.sidebar");
  const municipalityCode = useChatStore((s) => s.municipalityCode);
  const [data, setData] = useState<ElectoralListsByCommune | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedList, setSelectedList] = useState<ElectoralList | null>(null);
  const [hasNoData, setHasNoData] = useState(false);

  useEffect(() => {
    if (!municipalityCode) {
      setData(null);
      setSelectedList(null);
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
  }, [municipalityCode]);

  const handleSelectList = useCallback((list: ElectoralList) => {
    setSelectedList((prev) =>
      prev?.panel_number === list.panel_number ? null : list,
    );
  }, []);

  if (!municipalityCode) return null;

  return (
    <div className="flex flex-col gap-2 px-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase">
          {t("lists")}
        </span>
        {data && (
          <span className="text-xs text-muted-foreground">
            {data.commune_name} · {data.list_count} {t("lists")}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-4">
          <div className="size-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}

      {hasNoData && !isLoading && (
        <div className="flex flex-col gap-2 px-2 py-4 text-center">
          <span className="text-sm text-muted-foreground">
            {t("noElectoralData")}
          </span>
          <span className="text-xs text-muted-foreground">
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
              isSelected={selectedList?.panel_number === list.panel_number}
              onSelect={handleSelectList}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default SidebarElectoralLists;
