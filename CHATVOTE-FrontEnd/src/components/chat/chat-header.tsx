"use client";

import React, { useState } from "react";

import DonationDialog from "@components/donation-dialog";
import HowToDialog from "@components/guide-dialog";
import { LanguageSwitcher } from "@components/i18n/LanguageSwitcher";
import { Button } from "@components/ui/button";
import { SidebarTrigger } from "@components/ui/sidebar";
import { IS_EMBEDDED } from "@lib/utils";
import { Heart, HelpCircleIcon, XIcon } from "lucide-react";

import { useSearchParams } from "next/navigation";

import { AI_SDK_ENABLED } from "@lib/ai/feature-flags";

import ChatEmbedHeader from "./chat-embed-header";
import { ChatModeToggle } from "./chat-mode-toggle";
import CreateNewChatDropdownButton from "./create-new-chat-dropdown-button";
import SocketDisconnectedBanner from "./socket-disconnected-banner";
import { ThemeModeToggle } from "./theme-mode-toggle";

function ChatHeader() {
  const [displayBanner, setDisplayBanner] = useState(true);
  const params = useSearchParams();
  const urlModeOverride = params.get("mode") === "ai";
  // Show toggle only when env-flag enabled AND not forced via URL param
  const showToggle = AI_SDK_ENABLED && !urlModeOverride;

  if (IS_EMBEDDED) {
    return <ChatEmbedHeader />;
  }

  return (
    <React.Fragment>
      <header>
        {displayBanner === true && (
          <div
            className={
              "bg-primary text-primary-foreground flex w-full flex-col items-center justify-between gap-4 px-4 py-3 md:flex-row"
            }
          >
            <div className={"flex justify-between gap-3 md:gap-0"}>
              <div className={"text-sm"}>
                ChatVote est une initiative associative open source et
                souveraine - la fiabilité de l&apos;information fournie est
                notre priorité. Version 1.0
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
                <Button size="sm" data-sidebar="donation" variant="donation">
                  <Heart />
                  <div>Aidez-nous à aider la démocratie !</div>
                </Button>
              </DonationDialog>
            </div>
          </div>
        )}
        <div className="border-border flex h-10 w-full flex-none items-center justify-center border-b px-4">
          <a
            href="https://zap.ai"
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground flex items-center gap-1.5 text-xs transition-colors"
          >
            <span>Sponsorisé par</span>
            <span className="font-semibold">Zaq.ai</span>
            <span className="bg-primary/10 text-primary rounded px-1.5 py-0.5 text-[10px] font-medium">Sponsor</span>
          </a>
        </div>
        <div className="flex h-16 w-full flex-none items-center justify-between gap-1 px-4">
          {/* Left side - Logo, Home, Theme, Language, Sidebar Toggle */}
          <div className="flex items-center gap-1">
            <div className="block md:hidden">
              <SidebarTrigger className={"bg-primary"} />
            </div>
            <ThemeModeToggle />
            <LanguageSwitcher />
            {showToggle && <ChatModeToggle />}
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
