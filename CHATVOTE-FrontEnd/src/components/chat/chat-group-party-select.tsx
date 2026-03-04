"use client";

import React, { useState } from "react";

import { Modal } from "@components/ui/modal";
import { useTranslations } from "next-intl";

import ChatGroupPartySelectContent from "./chat-group-party-select-content";

type Props = {
  children: React.ReactNode;
  onNewChat?: (partyIds: string[]) => void;
  selectedPartyIdsInStore?: string[];
  addPartiesToChat?: boolean;
};

const ChatGroupPartySelect = ({
  children,
  onNewChat,
  selectedPartyIdsInStore,
  addPartiesToChat,
}: Props) => {
  const t = useTranslations("chat.groupSelect");
  const [isOpen, setIsOpen] = useState(false);

  const handleNewChat = (partyIds: string[]) => {
    setIsOpen(false);
    onNewChat?.(partyIds);
  };

  return (
    <React.Fragment>
      <div onClick={() => setIsOpen(true)}>{children}</div>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        className="w-full max-w-lg p-6"
      >
        <div className="mb-4 text-left">
          <h2 className="text-lg font-semibold">{t("partySelection")}</h2>
          <p className="text-muted-foreground text-sm">
            {addPartiesToChat ? t("modifyParties") : t("selectParties")}
          </p>
        </div>
        <ChatGroupPartySelectContent
          selectedPartyIdsInStore={selectedPartyIdsInStore}
          onNewChat={handleNewChat}
          addPartiesToChat={addPartiesToChat}
        />
      </Modal>
    </React.Fragment>
  );
};

export default ChatGroupPartySelect;
