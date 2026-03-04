"use client";

import PartyCards from "@components/party-cards";
import { useSidebar } from "@components/ui/sidebar";

function SidebarNewChatButtons() {
  const { setOpen } = useSidebar();

  const handleNewChat = () => {
    setOpen(false);
  };

  return (
    <PartyCards
      gridColumns={3}
      selectable={false}
      showChatvoteButton={true}
      onSelectParty={handleNewChat}
    />
  );
}

export default SidebarNewChatButtons;
