"use client";

import { forwardRef, useImperativeHandle, useMemo, useState } from "react";

import { useAppContext } from "@components/providers/app-provider";
import { Button } from "@components/ui/button";
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerTitle,
  DrawerTrigger,
} from "@components/ui/drawer";
import { Sheet, SheetContent, SheetTrigger } from "@components/ui/sheet";
import { type VotingBehavior } from "@lib/stores/chat-store.types";
import { track } from "@vercel/analytics/react";
import { ScrollTextIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import VisuallyHidden from "../visually-hidden";

import ChatVotingBehaviorDetailView from "./chat-voting-behavior-detail-view";

type Props = {
  votingBehavior: VotingBehavior;
  partyId: string;
};

export type ChatVotingBehaviorDetailButtonRef = {
  open: (voteId: string) => void;
};

const ChatVotingBehaviorDetailButton = forwardRef<
  ChatVotingBehaviorDetailButtonRef,
  Props
>(({ votingBehavior, partyId }: Props, ref) => {
  const t = useTranslations("chat");
  const [isOpen, setIsOpen] = useState(false);
  const [voteId, setVoteId] = useState<string | null>(null);
  const { device } = useAppContext();
  const isDesktop = device === "desktop" || device === "tablet";

  const triggerButton = (
    <Button
      variant="outline"
      className="h-8 px-2 text-xs group-data-has-message-background:bg-zinc-100 group-data-has-message-background:hover:bg-zinc-200 group-data-has-message-background:dark:bg-zinc-900 group-data-has-message-background:dark:hover:bg-zinc-800"
    >
      <ScrollTextIcon />
      {t("actions.showVotes")}
    </Button>
  );

  const voteIdsReferenced = useMemo(() => {
    const regex = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
    const matches = votingBehavior.summary.match(regex);

    const numbers = matches?.flatMap((match) => {
      const numbers = match.match(/^\[(\d+(?:\s*,\s*\d+)*)\]$/);

      if (!numbers) return [];
      const numbersArray = numbers[1].split(",");
      return numbersArray.map((number) => Number.parseInt(number));
    });

    const uniqueNumbers = [...new Set(numbers)];

    return uniqueNumbers.filter((number) =>
      votingBehavior.votes.some((vote) => vote.id === number.toString()),
    );
  }, [votingBehavior.summary, votingBehavior.votes]);

  const votes = useMemo(() => {
    return votingBehavior.votes.filter((vote) =>
      voteIdsReferenced.includes(Number(vote.id)),
    );
  }, [voteIdsReferenced, votingBehavior.votes]);

  useImperativeHandle(ref, () => ({
    open: (voteId) => {
      setIsOpen(true);
      setVoteId(voteId);
      track("voting_behavior_detail_button_clicked", {
        voteId,
      });
    },
  }));

  if (votes.length === 0) return <div />;

  const initialIndex = votes.findIndex((vote) => vote.id === voteId);

  if (isDesktop) {
    return (
      <Sheet open={isOpen} onOpenChange={setIsOpen}>
        <SheetTrigger asChild>{triggerButton}</SheetTrigger>
        <SheetContent className="w-[90vw] max-w-[700px]! p-0">
          <VisuallyHidden>
            <h2>{t("actions.votingBehavior")}</h2>
            <p>
              {t("votingBehavior.containsVotingInfo")}{" "}
              {t("votingBehavior.partyVotingBehavior")}{" "}
              {t("votingBehavior.ofTheParty")}
            </p>
          </VisuallyHidden>

          <ChatVotingBehaviorDetailView
            votes={votes}
            startIndex={initialIndex}
            partyId={partyId}
          />
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <Drawer open={isOpen} onOpenChange={setIsOpen}>
      <DrawerTrigger asChild>{triggerButton}</DrawerTrigger>
      <DrawerContent className="h-[95dvh]">
        <VisuallyHidden>
          <DrawerTitle>{t("actions.votingBehavior")}</DrawerTitle>
          <DrawerDescription>
            {t("votingBehavior.containsVotingInfo")}{" "}
            {t("votingBehavior.partyVotingBehavior")}{" "}
            {t("votingBehavior.ofTheParty")}
          </DrawerDescription>
        </VisuallyHidden>

        <ChatVotingBehaviorDetailView
          votes={votes}
          startIndex={initialIndex}
          partyId={partyId}
        />
      </DrawerContent>
    </Drawer>
  );
});

ChatVotingBehaviorDetailButton.displayName = "ChatVotingBehaviorDetailButton";

export default ChatVotingBehaviorDetailButton;
