import { useEffect } from "react";

import { useChatStore } from "@components/providers/chat-store-provider";
import { useCarousel } from "@components/ui/carousel";

type Props = {
  messageId: string;
  isExpanded: boolean;
};

function ChatGroupVotingBehaviorEmblaReinit({ messageId, isExpanded }: Props) {
  const embla = useCarousel();
  const isLoadingVotingBehavior = useChatStore(
    (state) => state.loading.votingBehaviorSummary === messageId,
  );
  const currentStreamedVotingBehavior = useChatStore(
    (state) => state.currentStreamedVotingBehavior,
  );

  useEffect(() => {
    (async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
      embla.api?.reInit();
    })();
  }, [
    embla.api,
    isLoadingVotingBehavior,
    isExpanded,
    currentStreamedVotingBehavior,
  ]);

  return null;
}

export default ChatGroupVotingBehaviorEmblaReinit;
