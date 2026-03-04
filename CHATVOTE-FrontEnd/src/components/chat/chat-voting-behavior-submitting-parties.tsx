"use client";

import { useMemo } from "react";

import Image from "next/image";

import { type Vote } from "@lib/socket.types";
import { buildPartyImageUrl } from "@lib/utils";
import { useTranslations } from "next-intl";

import { useParties } from "../providers/parties-provider";

type Props = {
  vote: Vote;
};

function ChatVotingBehaviorSubmittingParties({ vote }: Props) {
  const t = useTranslations("chat.votingBehavior");
  const parties = useParties();

  const submittingParties = useMemo(() => {
    return (vote.submitting_parties ?? [])
      .map((party) => parties?.find((p) => p?.party_id === party))
      .filter((p) => p !== undefined);
  }, [vote.submitting_parties, parties]);

  return (
    <>
      <p className="pt-4 pb-2 text-sm font-bold">
        {(vote.submitting_parties ?? []).length > 1
          ? t("submittingParties")
          : t("submittingParty")}
      </p>

      <div className="flex flex-row flex-wrap gap-2">
        {submittingParties.map((party) => (
          <div
            className="bg-muted flex flex-row items-center gap-2 rounded-full p-2 text-xs"
            key={party.party_id}
          >
            <div
              className="relative flex size-6 items-center justify-center rounded-full"
              style={{
                backgroundColor: party.background_color,
              }}
            >
              <Image
                src={buildPartyImageUrl(party.party_id)}
                alt={party.name}
                sizes="20px"
                fill
                className="rounded-full object-contain"
              />
            </div>
            {party.name}
          </div>
        ))}
      </div>
    </>
  );
}

export default ChatVotingBehaviorSubmittingParties;
