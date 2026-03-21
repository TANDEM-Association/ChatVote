import { Suspense } from "react";

import AiDisclaimer from "@components/legal/ai-disclaimer";
import LoadingSpinner from "@components/loading-spinner";
import {
  getAuth,
  getAiChatMessages,
  getChatSession,
  getSystemStatus,
} from "@lib/firebase/firebase-server";
import ChatSidebar from "./sidebar/chat-sidebar";
import ChatSidebarDesktop from "./sidebar/chat-sidebar-desktop";
import ChatContextSidebar from "./chat-context-sidebar";
import ChatDynamicChatInput from "./chat-dynamic-chat-input";
import MobileElectoralListsBar from "./mobile-electoral-lists-bar";
import ChatHeader from "./chat-header";
import ChatMainContent from "./chat-main-content";
import ChatInputGate from "./chat-input-gate";
import ChatScrollDownIndicator from "./chat-scroll-down-indicator";
import ChatViewSsr from "./chat-view-ssr";
import ChatViewSwitcher from "./chat-view-switcher";
import DevMetadataSidebarWrapper from "./dev-metadata-sidebar-wrapper";

type Props = {
  sessionId?: string;
  partyIds?: string[];
  initialQuestion?: string;
  municipalityCode?: string;
};

async function ChatView({
  sessionId,
  partyIds,
  initialQuestion,
  municipalityCode,
}: Props) {
  const [systemStatus, auth, chatSession] = await Promise.all([
    getSystemStatus(),
    getAuth(),
    sessionId ? getChatSession(sessionId) : Promise.resolve(undefined),
  ]);

  const sessionMode = chatSession?.mode;

  const aiMessages =
    sessionId && sessionMode === "ai"
      ? await getAiChatMessages(sessionId)
      : undefined;

  return (
    <div className="relative flex size-full h-full items-stretch overflow-hidden">
      {/* Sidebar - full panel on desktop, overlay on mobile */}
      <ChatSidebar />
      <ChatSidebarDesktop auth={auth} />
      <ChatContextSidebar />
      <Suspense fallback={null}>
        <DevMetadataSidebarWrapper />
      </Suspense>
      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        <ChatHeader />
        {/* Main content - adds padding when sidebar is expanded */}
        <ChatMainContent>
          <ChatViewSwitcher sessionId={sessionId} municipalityCode={municipalityCode} sessionMode={sessionMode} initialMessages={aiMessages}>
            <Suspense
              fallback={
                <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2">
                  <LoadingSpinner />
                  <p className="text-muted-foreground text-center text-sm">
                    Loading Chat Session...
                  </p>
                </div>
              }
            >
              <ChatViewSsr
                chatId={sessionId}
                partyIds={partyIds}
                initialQuestion={initialQuestion}
                municipalityCode={municipalityCode}
              />
            </Suspense>
            <ChatInputGate municipalityCode={municipalityCode}>
              <div className="bg-background relative mx-auto w-full max-w-192 shrink-0 p-3 md:p-4">
                <ChatScrollDownIndicator />
                <MobileElectoralListsBar />
                <ChatDynamicChatInput
                  initialSystemStatus={systemStatus}
                  hasValidServerUser={
                    auth.session !== null && !auth.session.isAnonymous
                  }
                  municipalityCode={municipalityCode}
                  sessionId={sessionId}
                />
                <AiDisclaimer />
              </div>
            </ChatInputGate>
          </ChatViewSwitcher>
        </ChatMainContent>
      </div>
    </div>
  );
}

export default ChatView;
