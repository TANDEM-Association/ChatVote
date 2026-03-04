"use client";

import { useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
} from "@components/ui/dropdown-menu";
import { useTranslations } from "next-intl";

import PartyCards from "../party-cards";

import CreateNewChatDropdownButtonTrigger from "./create-new-chat-dropdown-button-trigger";

function CreateNewChatDropdownButton() {
  const t = useTranslations("common");
  const [open, setOpen] = useState(false);

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <CreateNewChatDropdownButtonTrigger
        onTriggerClick={() => setOpen(true)}
      />
      <DropdownMenuContent
        align="end"
        className="w-[80vw] max-w-[300px] bg-purple-900 p-3"
      >
        <div className="mb-2 flex flex-col">
          <h2 className="text-lg font-bold">{t("newChat")}</h2>
          <p className="text-muted-foreground text-sm">{t("createNewChat")}</p>
        </div>
        <PartyCards
          gridColumns={3}
          selectable={false}
          onSelectParty={() => {
            setOpen(false);
          }}
          showChatvoteButton={true}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default CreateNewChatDropdownButton;
