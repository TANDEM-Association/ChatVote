import { useMemo } from "react";

import useCarouselCurrentIndex from "@lib/hooks/use-carousel-current-index";
import { type Vote } from "@lib/socket.types";

import AnimateTextOverflow from "./animate-text-overflow";

type Props = {
  votes: Vote[];
};

function ChatVoteDetailsHeader({ votes }: Props) {
  const selectedIndex = useCarouselCurrentIndex();

  const vote = votes[selectedIndex];

  const formattedDate = useMemo(() => {
    return new Date(vote.date).toLocaleDateString("de-DE", {
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  }, [vote.date]);

  return (
    <div className="border-border border-b pt-6 pb-4 text-center md:text-left">
      <AnimateTextOverflow>{vote.title}</AnimateTextOverflow>
      <p className="text-muted-foreground text-center text-xs">
        {formattedDate}
      </p>
    </div>
  );
}

export default ChatVoteDetailsHeader;
