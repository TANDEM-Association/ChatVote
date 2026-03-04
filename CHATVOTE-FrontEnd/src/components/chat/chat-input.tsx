"use client";

import { useAnonymousAuth } from "@components/anonymous-auth";
import { useChatStore } from "@components/providers/chat-store-provider";
import { Button } from "@components/ui/button";
import { cn } from "@lib/utils";
import { ArrowUp } from "lucide-react";
import { useTranslations } from "next-intl";

import ChatInputAddPartiesButton from "./chat-input-add-parties-button";
import MessageLoadingBorderTrail from "./message-loading-border-trail";

type Props = {
  disabled?: boolean;
};

const ChatInput = ({ disabled }: Props) => {
  const t = useTranslations("chat");
  const { user } = useAnonymousAuth();
  const input = useChatStore((state) => state.input);
  const setInput = useChatStore((state) => state.setInput);
  const addUserMessage = useChatStore((state) => state.addUserMessage);
  const quickReplies = useChatStore((state) => state.currentQuickReplies);
  const loading = useChatStore((state) => {
    const loading = state.loading;
    return (
      loading.general ||
      loading.newMessage ||
      loading.chatSession ||
      loading.initializingChatSocketSession
    );
  });

  const handleSubmit = async (
    event: React.FormEvent<HTMLFormElement> | string,
  ) => {
    let effectiveInput = input;

    if (typeof event === "string") {
      effectiveInput = event;
    } else {
      event.preventDefault();
    }

    if (!user?.uid || !effectiveInput.trim()) return;

    addUserMessage(user.uid, effectiveInput);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInput(e.target.value);
  };

  const handleQuickReplyClick = (reply: string) => {
    handleSubmit(reply);
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-disabled={disabled}
      data-testid={user?.uid ? "chat-form-ready" : undefined}
      className={cn(
        "relative w-full overflow-hidden rounded-4xl border border-purple-400 bg-purple-500 transition-colors focus-within:border-zinc-300 dark:focus-within:border-zinc-700",
        quickReplies?.length > 0 && "rounded-2xl",
      )}
    >
      {quickReplies.length > 0 && !disabled && (
        <>
          <ChatInputAddPartiesButton disabled={loading} />
          <div
            className={cn(
              "ml-7 flex gap-1 overflow-x-auto px-2 pt-2 whitespace-nowrap [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
              loading && "z-0 opacity-50",
            )}
          >
            {quickReplies.map((r) => (
              <button
                key={r}
                className="bg-muted enabled:hover:bg-muted/50 shrink-0 rounded-full px-2 py-1 transition-colors disabled:cursor-not-allowed"
                onClick={() => handleQuickReplyClick(r)}
                disabled={loading}
                type="button"
              >
                <p className="line-clamp-1 text-xs">{r}</p>
              </button>
            ))}
          </div>
        </>
      )}

      {loading && <MessageLoadingBorderTrail />}

      <div
        className={cn(
          "items flex w-full items-start gap-4 overflow-hidden px-4 py-3",
        )}
      >
        <input
          className="placeholder:text-muted-foreground flex-1 text-base whitespace-pre focus-visible:ring-0 focus-visible:outline-none disabled:cursor-not-allowed"
          placeholder={t("placeholder")}
          onChange={handleChange}
          value={input}
          disabled={loading || !!disabled}
        />
        <Button
          type="submit"
          disabled={!input.length || loading || !!disabled}
          className={
            "bg-foreground text-background hover:bg-foreground/80 disabled:bg-foreground/20 disabled:text-muted flex size-8 flex-none items-center justify-center rounded-full transition-colors"
          }
        >
          <ArrowUp className="size-4 font-bold" />
        </Button>
      </div>
    </form>
  );
};

export default ChatInput;
