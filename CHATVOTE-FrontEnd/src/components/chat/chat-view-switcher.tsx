"use client";

import { useSearchParams } from "next/navigation";

import { AI_SDK_ENABLED } from "@lib/ai/feature-flags";
import { useAppContext } from "@components/providers/app-provider";

import AiSdkChatView from "./ai-sdk/ai-sdk-chat-view";

type AiMessage = { role: string; content: string };

type Props = {
  sessionId?: string;
  municipalityCode?: string;
  sessionMode?: "ai" | "socket";
  initialMessages?: AiMessage[];
  children: React.ReactNode;
};

/** Returns true when AI SDK mode should be active (env var, URL override, or session). */
export function useIsAiSdkActive(sessionMode?: string): boolean {
  const params = useSearchParams();
  const urlOverride = params.get("mode") === "ai";
  // For existing sessions: respect the stored mode (old socket chats stay socket)
  if (sessionMode === "socket") return false;
  if (sessionMode === "ai") return true;
  // For new chats (no session): use env var or URL override
  return AI_SDK_ENABLED || urlOverride;
}

/**
 * Client-side switcher between Classic (Socket.IO) and AI SDK chat modes.
 * Supports ?mode=ai URL param, session mode from Firestore, or store flag.
 */
export default function ChatViewSwitcher({ sessionId, municipalityCode, sessionMode, initialMessages, children }: Props) {
  const active = useIsAiSdkActive(sessionMode);
  const { locale } = useAppContext();

  if (active) {
    return (
      <AiSdkChatView
        chatId={sessionId}
        locale={locale}
        municipalityCode={municipalityCode}
        initialMessages={initialMessages}
      />
    );
  }

  return <>{children}</>;
}
