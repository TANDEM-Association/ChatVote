import { useEffect } from "react";

import { SCROLL_CONTAINER_ID } from "@lib/scroll-constants";
import { chatViewScrollToBottom } from "@lib/scroll-utils";

type Props = {
  children: React.ReactNode;
  hasMessages?: boolean;
};

function ChatMessagesScrollView({ children, hasMessages }: Props) {
  useEffect(() => {
    if (hasMessages) {
      chatViewScrollToBottom({ behavior: "instant" });
    }
  }, [hasMessages]);

  return (
    <div
      className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain lg:mx-auto lg:w-282"
      id={SCROLL_CONTAINER_ID}
    >
      {children}
    </div>
  );
}

export default ChatMessagesScrollView;
