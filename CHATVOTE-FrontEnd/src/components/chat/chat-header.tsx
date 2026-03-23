"use client";

import React, { useState } from "react";

import DonationDialog from "@components/donation-dialog";
import HowToDialog from "@components/guide-dialog";
import { LanguageSwitcher } from "@components/i18n/LanguageSwitcher";
import { Button } from "@components/ui/button";
import { SidebarTrigger } from "@components/ui/sidebar";

import { IS_EMBEDDED } from "@lib/utils";
import { Heart, HelpCircleIcon, Share, SquarePenIcon, XIcon } from "@components/icons";

import { useSearchParams } from "next/navigation";

import { AI_SDK_ENABLED } from "@lib/ai/feature-flags";
import { trackShareClicked } from "@lib/firebase/analytics";

import ChatEmbedHeader from "./chat-embed-header";
import { ChatModeToggle } from "./chat-mode-toggle";
import { ThemeModeToggle } from "./theme-mode-toggle";

function ChatHeader() {
  const [displayBanner, setDisplayBanner] = useState(true);
  const [shareCopied, setShareCopied] = useState(false);
  const params = useSearchParams();
  const urlModeOverride = params.get("mode") === "ai";
  // Toggle hidden — mode is now controlled by env var only
  const showToggle = false && AI_SDK_ENABLED && !urlModeOverride;
  const chatId = params.get("chat_id");

  const handleShare = async () => {
    const url = window.location.href;
    if (chatId) {
      trackShareClicked({ content_type: "chat_permalink", session_id: chatId });
    }
    if (navigator.canShare?.({ url })) {
      try {
        await navigator.share({ title: "Mon chat ChatVote", url });
      } catch {
        // User cancelled share sheet — ignore
      }
    } else {
      await navigator.clipboard.writeText(url);
      // Brief visual feedback via button text change handled by state
      setShareCopied(true);
      setTimeout(() => setShareCopied(false), 2000);
    }
  };

  if (IS_EMBEDDED) {
    return <ChatEmbedHeader />;
  }

  return (
    <React.Fragment>
      <header>
        {displayBanner === true && (
          <div
            className={
              "bg-primary text-primary-foreground flex w-full items-center justify-between gap-2 px-3 py-2 md:gap-4 md:px-4 md:py-3"
            }
          >
            <div className="min-w-0 flex-1 text-xs leading-tight lg:text-sm">
              <span className="hidden xl:inline">ChatVote est une initiative associative open source et
              souveraine - la fiabilité de l&apos;information fournie est
              notre priorité. Version 1.0</span>
              <span className="hidden md:inline xl:hidden">ChatVote - open source et souveraine</span>
              <span className="md:hidden">ChatVote - open source et souveraine. V1.0</span>
            </div>
            <div className="flex flex-none items-center gap-2">
              <Button data-sidebar="more" size="sm" className="hidden lg:inline-flex">
                <div>En savoir plus</div>
              </Button>
              <DonationDialog>
                <Button size="sm" data-sidebar="donation" variant="donation" className="whitespace-nowrap text-xs md:text-sm">
                  <Heart className="size-3.5 md:size-4" />
                  <span className="hidden sm:inline">Aidez-nous à aider la démocratie !</span>
                  <span className="sm:hidden">Soutenir</span>
                </Button>
              </DonationDialog>
              <Button
                variant="ghost"
                size="icon"
                className="size-7 flex-none md:hidden"
                onClick={() => setDisplayBanner(false)}
              >
                <XIcon className="size-3.5" />
              </Button>
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
            {showToggle && <ChatModeToggle />}
          </div>
          {/* Right side - Help, Share, New Chat */}
          <div className="flex items-center gap-1">
            <HowToDialog>
              <Button variant="ghost" size="icon" className="size-8">
                <HelpCircleIcon />
              </Button>
            </HowToDialog>
            {chatId && (
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={handleShare}
                title={shareCopied ? "Lien copié !" : "Partager ce chat"}
              >
                {shareCopied ? (
                  <span className="text-xs font-medium text-green-400">✓</span>
                ) : (
                  <Share className="size-4" />
                )}
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => window.location.href = '/chat'}
            >
              <SquarePenIcon className="size-3.5" />
              <span>Nouveau Chat</span>
            </Button>
          </div>
        </div>

      </header>

    </React.Fragment>
  );
}

export default ChatHeader;
