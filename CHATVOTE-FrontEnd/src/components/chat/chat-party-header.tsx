"use client";

import Image from "next/image";

import { type PartyDetails } from "@lib/party-details";

type Props = {
  parties?: PartyDetails[];
};

const ChatPartyHeader = ({ parties }: Props) => {
  if (parties === undefined || parties.length === 0 || parties.length > 1) {
    return null;
  }

  const party = parties[0];

  return (
    <div className="pointer-events-none sticky top-0 z-10 flex justify-center py-4">
      <div className="flex flex-col items-center gap-2">
        <div className="relative flex size-28 items-center justify-center rounded-md border bg-neutral-100 shadow-sm md:size-36">
          {party !== undefined ? (
            <Image
              alt={party.name}
              src={party.logo_url}
              fill
              sizes="(max-width: 768px) 40vw, 20vw"
              className="object-contain p-4"
            />
          ) : (
            <Image
              src="/images/logos/chatvote.svg"
              alt="chatvote"
              width={0}
              height={0}
              sizes="100vw"
              className="size-full p-4"
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatPartyHeader;
