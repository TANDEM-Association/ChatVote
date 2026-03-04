"use client";

import { type Vote } from "@lib/socket.types";
import { useTranslations } from "next-intl";

import { useChatVotingDetails } from "../providers/chat-voting-details-provider";

type Props = {
  vote: Vote;
};

function ChatVotingBehaviorDetailJustification({ vote }: Props) {
  const t = useTranslations("common");
  const { selectedPartyId } = useChatVotingDetails();

  const party = vote.voting_results.by_party.find(
    (p) => p.party === selectedPartyId,
  );

  if (party === undefined || party.justification === undefined) {
    return null;
  }

  return (
    <>
      <h2 className="pt-4 pb-2 text-base font-bold">{t("justification")}</h2>
      <p className="text-muted-foreground text-sm">{party.justification}</p>
    </>
  );
}

export default ChatVotingBehaviorDetailJustification;
