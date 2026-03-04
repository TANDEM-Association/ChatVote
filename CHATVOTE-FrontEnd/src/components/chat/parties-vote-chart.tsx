"use client";

import { useMemo } from "react";

import { type Vote } from "@lib/socket.types";
import { useTranslations } from "next-intl";

import { useChatVotingDetails } from "../providers/chat-voting-details-provider";
import { useParties } from "../providers/parties-provider";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

import VoteChart from "./vote-chart";

type Props = {
  vote: Vote;
};

function PartiesVoteChart({ vote }: Props) {
  const t = useTranslations("chat.voteChart");
  const { selectedPartyId, setSelectedPartyId } = useChatVotingDetails();

  const parties = useParties();
  const byParty = vote.voting_results.by_party;

  const partyNamesAndKeys = useMemo(() => {
    return byParty.map((party) => ({
      key: party.party,
      name:
        party.party === "fraktionslose"
          ? t("independents")
          : (parties?.find((p) => p.party_id === party.party)?.name ??
            party.party),
    }));
  }, [byParty, parties, t]);

  const selectedPartyData = useMemo(() => {
    return byParty.find((party) => party.party === selectedPartyId);
  }, [byParty, selectedPartyId]);

  if (selectedPartyData === undefined) {
    return null;
  }

  return (
    <section className="flex flex-1 flex-col items-center justify-center gap-4">
      <VoteChart
        voteResults={selectedPartyData}
        memberCount={selectedPartyData.members}
      />

      <div className="flex grow flex-col items-center justify-center">
        <Select
          defaultValue={selectedPartyId}
          value={selectedPartyId}
          onValueChange={setSelectedPartyId}
        >
          <SelectTrigger className="h-8 w-[130px] rounded-lg">
            <SelectValue placeholder={t("selectParty")} />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {partyNamesAndKeys.map((party) => {
                return (
                  <SelectItem key={party.key} value={party.key}>
                    {party.name}
                  </SelectItem>
                );
              })}
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>
    </section>
  );
}

export default PartiesVoteChart;
