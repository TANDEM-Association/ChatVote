"use client";

import { useAnonymousAuth } from "@components/anonymous-auth";
import LoginButton from "@components/auth/login-button";
import { useChatStore } from "@components/providers/chat-store-provider";
import { Button } from "@components/ui/button";
import { cn } from "@lib/utils";
import { useTranslations } from "next-intl";

import MessageLoadingBorderTrail from "./message-loading-border-trail";

function ChatInputRateLimit() {
  const t = useTranslations("common");
  const tNav = useTranslations("navigation");
  const { user } = useAnonymousAuth();
  const input = useChatStore((state) => state.input);
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

  const handleQuickReplyClick = (reply: string) => {
    handleSubmit(reply);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border-input bg-muted relative w-full overflow-hidden rounded-lg border py-3 md:py-4"
    >
      {quickReplies.length > 0 && (
        <div
          className={cn(
            "flex gap-1 overflow-x-auto px-3 whitespace-nowrap [-ms-overflow-style:none] [scrollbar-width:none] md:px-4 [&::-webkit-scrollbar]:hidden",
            loading && "z-0 opacity-50",
          )}
        >
          {quickReplies.map((r) => (
            <button
              key={r}
              className="shrink-0 rounded-full bg-zinc-200 px-2 py-1 transition-colors enabled:hover:bg-zinc-300 disabled:cursor-not-allowed dark:bg-zinc-900 dark:enabled:hover:bg-zinc-950"
              onClick={() => handleQuickReplyClick(r)}
              disabled={loading}
              type="button"
            >
              <p className="line-clamp-1 text-xs">{r}</p>
            </button>
          ))}
        </div>
      )}

      <section
        className={cn(
          "flex flex-col px-3 md:px-4",
          quickReplies.length > 0 && "mt-2",
        )}
      >
        <div className="flex items-center gap-2">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-yellow-400 opacity-75" />
            <span className="relative inline-flex size-2 rounded-full bg-yellow-500" />
          </span>
          <h2 className="font-bold">{t("serverOverloaded")}</h2>
        </div>
        <p className="text-muted-foreground text-sm">
          {t("serverOverloadedDescription")}
        </p>
        <LoginButton
          isAuthenticated={false}
          noUserChildren={
            <Button size="sm" className="mt-2">
              {tNav("login")}
            </Button>
          }
        />
      </section>

      {loading && <MessageLoadingBorderTrail />}
    </form>
  );
}

export default ChatInputRateLimit;
