"use client";

import useCarouselCurrentIndex from "@lib/hooks/use-carousel-current-index";
import { type Vote } from "@lib/socket.types";
import { useTranslations } from "next-intl";

type Props = {
  votes: Vote[];
};

function ChatVoteDetailsSlideCounter({ votes }: Props) {
  const t = useTranslations("common");
  const selectedIndex = useCarouselCurrentIndex();

  return (
    <div className="flex flex-col items-center justify-center">
      <p className="text-sm font-bold">
        {selectedIndex + 1} / {votes.length}
      </p>
      <span className="text-muted-foreground text-xs">{t("votes")}</span>
    </div>
  );
}

export default ChatVoteDetailsSlideCounter;
