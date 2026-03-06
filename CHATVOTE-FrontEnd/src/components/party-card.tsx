"use client";

import React from "react";

import Image from "next/image";
import Link from "next/link";

import { type PartyDetails } from "@lib/party-details";
import { cn } from "@lib/utils";
import { CheckIcon } from "lucide-react";

import { Button } from "./ui/button";

type Props = {
  id: string;
  party: PartyDetails;
  isSelected?: boolean;
  onSelectParty?: (partyId: string) => void;
  selectable?: boolean;
};

function PartyCard({
  id,
  party,
  isSelected,
  onSelectParty,
  selectable = true,
}: Props) {
  const { name } = party;

  return (
    <Button
      className="relative flex aspect-square h-fit w-full items-center justify-center overflow-hidden border bg-neutral-100 transition-all duration-300 ease-in-out hover:bg-purple-100"
      onClick={
        selectable === true
          ? () => {
              onSelectParty?.(id);
            }
          : undefined
      }
      asChild={selectable === false}
    >
      {selectable === true ? (
        <React.Fragment>
          <div
            className={cn(
              "absolute top-2 right-2 rounded-full border border-zinc-700 bg-zinc-800 p-[2px] transition-all duration-100 ease-in-out",
              isSelected === true
                ? "scale-100 opacity-100"
                : "scale-75 opacity-0",
            )}
          >
            <CheckIcon className="size-2 text-white" />
          </div>
          <Image
            alt={name}
            src={party.logo_url}
            sizes="20vw"
            width={0}
            height={0}
            loading="eager"
            className="object-containn size-16"
          />
        </React.Fragment>
      ) : (
        <Link href={`/chat?party_id=${id}`} onClick={() => onSelectParty?.(id)}>
          <Image
            alt={name}
            src={party.logo_url}
            sizes="20vw"
            width={0}
            height={0}
            loading="eager"
            className="object-containn size-16"
          />
        </Link>
      )}
    </Button>
  );
}

export default PartyCard;
