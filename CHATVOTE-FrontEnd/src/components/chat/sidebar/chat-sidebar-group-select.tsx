"use client";

import ChatGroupPartySelect from "@components/chat/chat-group-party-select";
import { Button } from "@components/ui/button";
import { useSidebar } from "@components/ui/sidebar";
import { GitCompareArrows } from "lucide-react";
import { useTranslations } from "next-intl";

type Props = {
  iconOnly?: boolean;
};

const ChatSidebarGroupSelect = ({ iconOnly }: Props) => {
  const t = useTranslations("chat.sidebar");
  const { setOpen } = useSidebar();

  const handleNewChat = () => {
    setOpen(false);

    // hacky fix since the sidebar collides with the drawer's pointer events settings
    setTimeout(() => {
      if (document) {
        document.body.style.pointerEvents = "auto";
      }
    }, 500);
  };

  return (
    <ChatGroupPartySelect onNewChat={handleNewChat}>
      <Button
        className={
          iconOnly
            ? "size-10"
            : "mt-4 flex w-full items-center justify-center gap-2"
        }
      >
        <GitCompareArrows />
        {iconOnly ? null : <div>{t("compareParties")}</div>}
      </Button>
    </ChatGroupPartySelect>
  );
};

export default ChatSidebarGroupSelect;
