import React from "react";

import HowToDialog from "@components/guide-dialog";
import { LanguageSwitcher } from "@components/i18n/LanguageSwitcher";
import { Button } from "@components/ui/button";
import { SidebarTrigger } from "@components/ui/sidebar";
import { IS_EMBEDDED } from "@lib/utils";
import { HelpCircleIcon } from "lucide-react";

import ChatEmbedHeader from "./chat-embed-header";
import CreateNewChatDropdownButton from "./create-new-chat-dropdown-button";
import SocketDisconnectedBanner from "./socket-disconnected-banner";
import { ThemeModeToggle } from "./theme-mode-toggle";

function ChatHeader() {
  if (IS_EMBEDDED) {
    return <ChatEmbedHeader />;
  }

  return (
    <React.Fragment>
      <header className="flex h-16 w-full flex-none items-center justify-between gap-1 px-4">
        {/* Left side - Logo, Home, Theme, Language, Sidebar Toggle */}
        <div className="flex items-center gap-1">
          <div className="block md:hidden">
            <SidebarTrigger className={"bg-primary"} />
          </div>
          <ThemeModeToggle />
          <LanguageSwitcher />
        </div>
        {/* Right side - Help, Share, New Chat */}
        <div className="flex items-center gap-1">
          <HowToDialog>
            <Button variant="ghost" size="icon" className="size-8">
              <HelpCircleIcon />
            </Button>
          </HowToDialog>
          <CreateNewChatDropdownButton />
        </div>
      </header>

      <SocketDisconnectedBanner />
    </React.Fragment>
  );
}

export default ChatHeader;
