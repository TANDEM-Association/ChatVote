"use client";

import { useEffect, useState } from "react";

import { Button } from "@components/ui/button";
import { SCROLL_CONTAINER_ID } from "@lib/scroll-constants";
import { chatViewScrollToBottom } from "@lib/scroll-utils";
import { cn } from "@lib/utils";
import { ArrowDownIcon } from "lucide-react";

function ChatScrollDownIndicator() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (!document) return;

    const scrollContainer = document.getElementById(SCROLL_CONTAINER_ID);
    if (!scrollContainer) return;

    const handleScroll = () => {
      const isScrolled =
        scrollContainer.scrollTop +
          scrollContainer.clientHeight -
          scrollContainer.scrollHeight <
        -1;
      setIsVisible(isScrolled);
    };

    scrollContainer.addEventListener("scroll", handleScroll);
    scrollContainer.addEventListener("resize", handleScroll);

    return () => {
      scrollContainer.removeEventListener("scroll", handleScroll);
      scrollContainer.removeEventListener("resize", handleScroll);
    };
  }, [isVisible]);

  const handleClick = () => {
    chatViewScrollToBottom();
  };

  return (
    <div
      className={cn(
        "pointer-events-none absolute inset-x-4 -top-10 flex justify-end",
      )}
    >
      <Button
        variant="default"
        className={cn(
          "bg-background border-border dark:hover:bg-muted size-8 rounded-full border shadow-xl hover:bg-zinc-100 dark:bg-zinc-900",
          "z-40 transition-all duration-200 ease-in-out",
          "md:hover:-translate-y-1 md:hover:scale-110",
          isVisible
            ? "pointer-events-auto translate-y-0 scale-100 opacity-100"
            : "pointer-events-none translate-y-2 scale-0 opacity-0",
        )}
        onClick={handleClick}
        size="icon"
      >
        <ArrowDownIcon className="text-muted-foreground size-4" />
      </Button>
    </div>
  );
}

export default ChatScrollDownIndicator;
