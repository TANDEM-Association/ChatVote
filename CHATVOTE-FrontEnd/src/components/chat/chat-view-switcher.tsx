"use client";

import { useAppContext } from "@components/providers/app-provider";

import AiSdkChatView from "./ai-sdk/ai-sdk-chat-view";

type AiMessage = { role: string; content: string; parts?: Array<Record<string, unknown>> };

type Props = {
  sessionId?: string;
  municipalityCode?: string;
  initialMessages?: AiMessage[];
};

/**
 * Renders the AI SDK chat view. Socket.IO mode has been removed.
 */
export default function ChatViewSwitcher({ sessionId, municipalityCode, initialMessages }: Props) {
  const { locale } = useAppContext();

  return (
    <AiSdkChatView
      chatId={sessionId}
      locale={locale}
      municipalityCode={municipalityCode}
      initialMessages={initialMessages}
    />
  );
}
