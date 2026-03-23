import { Suspense } from "react";

import {
  getAuth,
  getAiChatMessages,
} from "@lib/firebase/firebase-server";
import ChatSidebar from "./sidebar/chat-sidebar";
import ChatSidebarDesktop from "./sidebar/chat-sidebar-desktop";
import ChatContextSidebar from "./chat-context-sidebar";
import ChatHeader from "./chat-header";
import ChatMainContent from "./chat-main-content";
import ChatViewSwitcher from "./chat-view-switcher";
import DevMetadataSidebarWrapper from "./dev-metadata-sidebar-wrapper";

type Props = {
  sessionId?: string;
  municipalityCode?: string;
};

async function ChatView({
  sessionId,
  municipalityCode,
}: Props) {
  const [auth, aiMessages] = await Promise.all([
    getAuth(),
    sessionId ? getAiChatMessages(sessionId) : Promise.resolve(undefined),
  ]);

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
          <ChatViewSwitcher sessionId={sessionId} municipalityCode={municipalityCode} initialMessages={aiMessages} />
        </ChatMainContent>
      </div>
    </div>
  );
}

export default ChatView;
