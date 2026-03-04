"use client";

import { useState } from "react";

import Image from "next/image";
import Link from "next/link";

import PartyCard from "@components/party-card";
import { useParties } from "@components/providers/parties-provider";
import { cn } from "@lib/utils";
import { CircleXIcon, EllipsisIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "./ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "./ui/collapsible";

type Props = {
  className?: string;
  selectedPartyIds?: string[];
  onSelectParty?: (partyId: string) => void;
  selectable?: boolean;
  gridColumns?: number;
  showChatvoteButton?: boolean;
};

function PartyCards({
  className,
  selectedPartyIds,
  onSelectParty,
  selectable = true,
  gridColumns = 4,
  showChatvoteButton = false,
}: Props) {
  const t = useTranslations("common");
  const parties = useParties();

  const smallParties = parties.filter((party) => {
    return party.is_small_party === true;
  });
  const largeParties = parties.filter((party) => {
    return party.is_small_party === false;
  });

  const defaultShowMore = !!smallParties?.find((p) =>
    selectedPartyIds?.includes(p.party_id),
  );

  const [showMore, setShowMore] = useState(defaultShowMore);

  return (
    <Collapsible open={showMore} onOpenChange={setShowMore} asChild>
      <section
        className={cn("grid w-full grid-cols-4 gap-2", className)}
        style={{
          gridTemplateColumns: `repeat(${gridColumns}, minmax(0, 1fr))`,
        }}
      >
        {showChatvoteButton === true ? (
          <Button
            className={cn(
              "flex aspect-square size-full items-center justify-center rounded-md",
              "border-muted-foreground/20 bg-background hover:bg-muted border p-0 dark:bg-zinc-900",
            )}
            type="button"
            tooltip="chatvote"
            asChild
          >
            <Link href="/chat" onClick={() => onSelectParty?.("chatvote")}>
              <Image
                src="/images/logos/chatvote.svg"
                alt="chatvote"
                width={0}
                height={0}
                sizes="100vw"
                className="size-10"
                loading="eager"
              />
            </Link>
          </Button>
        ) : null}
        {largeParties?.map((party) => (
          <PartyCard
            id={party.party_id}
            key={party.party_id}
            party={party}
            isSelected={selectedPartyIds?.includes(party.party_id)}
            onSelectParty={onSelectParty}
            selectable={selectable}
          />
        ))}
        <CollapsibleTrigger asChild>
          <Button
            variant="secondary"
            className={cn(
              "flex aspect-square items-center justify-center",
              "border-muted-foreground/20 h-fit w-full overflow-hidden border md:hover:bg-zinc-200 dark:md:hover:bg-zinc-700",
              "text-muted-foreground flex flex-col items-center justify-center text-center whitespace-normal",
              "gap-1 text-xs md:gap-2 md:text-sm",
            )}
          >
            {showMore ? (
              <CircleXIcon className="size-4" />
            ) : (
              <EllipsisIcon className="size-4" />
            )}
            {gridColumns >= 4 &&
              (showMore ? t("lessParties") : t("moreParties"))}
          </Button>
        </CollapsibleTrigger>

        <CollapsibleContent asChild>
          <div
            className="col-span-4 grid gap-2"
            style={{
              gridColumn: `span ${gridColumns} / span ${gridColumns}`,
              gridTemplateColumns: `repeat(${gridColumns}, minmax(0, 1fr))`,
            }}
          >
            {smallParties?.map((party) => (
              <PartyCard
                id={party.party_id}
                key={party.party_id}
                party={party}
                isSelected={selectedPartyIds?.includes(party.party_id)}
                onSelectParty={onSelectParty}
                selectable={selectable}
              />
            ))}
          </div>
        </CollapsibleContent>
      </section>
    </Collapsible>
  );
}

export default PartyCards;
