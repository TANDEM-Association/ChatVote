"use client";

import { cx } from "class-variance-authority";
import { useTranslations } from "next-intl";

import AnimatedMessageSequence from "./animated-message-sequence";
import { ChatMessageIcon } from "./chat-message-icon";

const ThinkingMessage = () => {
  const t = useTranslations("chat.thinking");

  const messages = [
    t("searchingSources"),
    t("analyzingSources"),
    t("processingData"),
    t("generatingResults"),
    t("finalizing"),
  ];

  return (
    <div className={cx("flex items-center gap-3 md:gap-4")}>
      <ChatMessageIcon />

      <AnimatedMessageSequence
        className="text-muted-foreground"
        messages={messages}
      />
    </div>
  );
};

export default ThinkingMessage;
