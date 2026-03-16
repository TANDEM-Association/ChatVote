"use client";

import { useSearchParams } from "next/navigation";

import { AI_SDK_ENABLED } from "@lib/ai/feature-flags";
import { useChatModeStore } from "@lib/stores/chat-mode-store";
import { useAppContext } from "@components/providers/app-provider";

import AiSdkChatView from "./ai-sdk/ai-sdk-chat-view";

type Props = {
  sessionId?: string;
  municipalityCode?: string;
  children: React.ReactNode;
};

/** Returns true when AI SDK mode should be active (URL override or store). */
export function useIsAiSdkActive(): boolean {
  const params = useSearchParams();
  const { chatMode } = useChatModeStore();
  const urlOverride = params.get("mode") === "ai";
  return urlOverride || (AI_SDK_ENABLED && chatMode === "ai-sdk");
}

/**
 * Client-side switcher between Classic (Socket.IO) and AI SDK chat modes.
 * Supports ?mode=ai URL param to force AI SDK mode without env var.
 */
export default function ChatViewSwitcher({ sessionId, municipalityCode, children }: Props) {
  const active = useIsAiSdkActive();
  const { locale } = useAppContext();

  if (active) {
    return <AiSdkChatView chatId={sessionId} locale={locale} municipalityCode={municipalityCode} />;
  }

  return <>{children}</>;
}
