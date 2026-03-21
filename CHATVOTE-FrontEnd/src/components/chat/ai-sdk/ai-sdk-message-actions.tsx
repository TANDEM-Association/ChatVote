"use client";

import { useState } from "react";

import { Button } from "@components/ui/button";
import { cn } from "@lib/utils";
import { scoreFeedback } from "@lib/langfuse-web";
import { trackMessageCopied, trackMessageLiked, trackMessageDisliked } from "@lib/firebase/analytics";
import { track } from "@vercel/analytics/react";
import { Check, Copy, ThumbsUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import ChatDislikeFeedbackButton from "../chat-dislike-feedback-button";

type Props = {
  messageId: string;
  messageContent: string;
};

export default function AiSdkMessageActions({ messageId, messageContent }: Props) {
  const t = useTranslations("chat.copy");
  const [isCopied, setIsCopied] = useState(false);
  const [feedback, setFeedback] = useState<"like" | "dislike" | null>(null);
  const [feedbackDetail, setFeedbackDetail] = useState<string>();

  const handleCopy = () => {
    navigator.clipboard.writeText(messageContent);
    setIsCopied(true);
    toast.success(t("success"));
    track("message_copied", { message: messageContent });
    trackMessageCopied();
    setTimeout(() => setIsCopied(false), 2000);
  };

  const handleLike = () => {
    setFeedback("like");
    track("message_liked", { message: messageContent });
    trackMessageLiked({ session_id: messageId });
    scoreFeedback(messageId, "like");
  };

  const handleDislike = (details: string) => {
    setFeedback("dislike");
    setFeedbackDetail(details);
    track("message_disliked", { message: messageContent, details });
    trackMessageDisliked({ session_id: messageId, has_detail: details.length > 0 });
    scoreFeedback(messageId, "dislike", details || undefined);
  };

  return (
    <div className="text-muted-foreground mt-2 flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon"
        className="size-7"
        onClick={handleCopy}
      >
        {isCopied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="group/like size-7"
        onClick={handleLike}
      >
        <ThumbsUp className={cn("size-3.5", feedback === "like" && "fill-foreground/30")} />
      </Button>
      <ChatDislikeFeedbackButton
        isDisliked={feedback === "dislike"}
        onDislikeFeedback={handleDislike}
        feedbackDetail={feedbackDetail}
      />
    </div>
  );
}
