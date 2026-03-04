"use client";

import EmbedOpenWebsiteButton from "@components/embed-open-website-button";
import GuideDialog from "@components/guide-dialog";
import { Button } from "@components/ui/button";
import { SidebarTrigger } from "@components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@components/ui/tooltip";
import { HelpCircleIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import SocketDisconnectedBanner from "./socket-disconnected-banner";

function ChatEmbedHeader() {
  const t = useTranslations("common");

  return (
    <>
      <header className="min-h-chat-header border-b-muted bg-background relative z-10 flex w-full items-center gap-1 border-b px-4">
        <div className="flex min-w-0 grow items-center gap-2 overflow-x-hidden">
          <Tooltip>
            <TooltipTrigger asChild>
              <SidebarTrigger />
            </TooltipTrigger>
            <TooltipContent>{t("openMenu")}</TooltipContent>
          </Tooltip>
        </div>
        <div className="flex items-center gap-1">
          <GuideDialog>
            <Button variant="ghost" size="icon" className="size-8">
              <HelpCircleIcon />
            </Button>
          </GuideDialog>
          <EmbedOpenWebsiteButton />
        </div>
      </header>

      <SocketDisconnectedBanner />
    </>
  );
}

export default ChatEmbedHeader;
