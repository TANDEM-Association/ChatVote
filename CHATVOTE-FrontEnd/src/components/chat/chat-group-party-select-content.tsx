"use client";

import React, { useState } from "react";

import PartyCards from "@components/party-cards";
import { track } from "@vercel/analytics/react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import ChatGroupPartySelectSubmitButton from "./chat-group-party-select-submit-button";

type Props = {
  selectedPartyIdsInStore?: string[];
  onNewChat?: (partyIds: string[]) => void;
  addPartiesToChat?: boolean;
};

export const MAX_SELECTABLE_PARTIES = 7;

const ChatGroupPartySelectContent = ({
  selectedPartyIdsInStore,
  onNewChat,
  addPartiesToChat,
}: Props) => {
  const t = useTranslations("chat.groupSelect");
  const [selectedPartyIds, setSelectedPartyIds] = useState<string[]>(
    selectedPartyIdsInStore ?? [],
  );

  const handlePartyClicked = (partyId: string) => {
    if (selectedPartyIds.includes(partyId)) {
      setSelectedPartyIds((prevState) =>
        prevState.filter((id) => id !== partyId),
      );
      return;
    }

    if (selectedPartyIds.length >= MAX_SELECTABLE_PARTIES) {
      toast.error(
        t("maxPartiesError", { max: MAX_SELECTABLE_PARTIES }),
      );
      return;
    }

    setSelectedPartyIds((prevState) => {
      return [...prevState, partyId];
    });
  };

  const handleNewChat = () => {
    track("chat_group_party_select_submit", {
      party_ids: selectedPartyIds.join(","),
    });
    onNewChat?.(selectedPartyIds);
  };

  return (
    <React.Fragment>
      <PartyCards
        className="pb-2"
        onSelectParty={handlePartyClicked}
        selectedPartyIds={selectedPartyIds}
      />
      <div className="flex justify-end pt-2">
        <ChatGroupPartySelectSubmitButton
          selectedPartyIds={selectedPartyIds}
          onSubmit={handleNewChat}
          addPartiesToChat={addPartiesToChat}
        />
      </div>
    </React.Fragment>
  );
};

export default ChatGroupPartySelectContent;
