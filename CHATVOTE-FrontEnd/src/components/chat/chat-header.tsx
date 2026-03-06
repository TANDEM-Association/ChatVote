"use client";

import React, { useState } from "react";

import DonationDialog from "@components/donation-dialog";
import HowToDialog from "@components/guide-dialog";
import { LanguageSwitcher } from "@components/i18n/LanguageSwitcher";
import { Button } from "@components/ui/button";
import { SidebarTrigger } from "@components/ui/sidebar";
import { IS_EMBEDDED } from "@lib/utils";
import { Heart, HelpCircleIcon, XIcon } from "lucide-react";

import ChatEmbedHeader from "./chat-embed-header";
import CreateNewChatDropdownButton from "./create-new-chat-dropdown-button";
import SocketDisconnectedBanner from "./socket-disconnected-banner";
import { ThemeModeToggle } from "./theme-mode-toggle";

function ChatHeader() {
  const [displayBanner, setDisplayBanner] = useState(true);

  if (IS_EMBEDDED) {
    return <ChatEmbedHeader />;
  }

  return (
    <React.Fragment>
      <header>
        {displayBanner === true && (
          <div
            className={
              "flex w-full flex-col items-center justify-between gap-4 bg-purple-600 px-4 py-3 md:flex-row"
            }
          >
            <div className={"flex justify-between gap-3 md:gap-0"}>
              <div className={"text-sm"}>
                ChatVote est une initiative associative open source et
                souveraine - la fiabilité de l'information fournie sont notre
                priorité. Version. 1.0.
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="size-8 flex-none md:hidden"
                onClick={() => setDisplayBanner(false)}
              >
                <XIcon />
              </Button>
            </div>
            <div className={"flex flex-wrap items-center gap-3 md:flex-nowrap"}>
              <Button data-sidebar="more" size="sm">
                <div>En savoir plus</div>
              </Button>
              <DonationDialog>
                <Button size="sm" data-sidebar="donation" variant="secondary">
                  <Heart />
                  <div>Aidez-nous à aider la démocratie !</div>
                </Button>
              </DonationDialog>
            </div>
          </div>
        )}
        <div className="flex h-16 w-full flex-none items-center justify-between gap-1 px-4">
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
        </div>

        <SocketDisconnectedBanner />
      </header>
    </React.Fragment>
  );
}

export default ChatHeader;
