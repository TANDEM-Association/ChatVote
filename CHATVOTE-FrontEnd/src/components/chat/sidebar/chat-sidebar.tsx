import { getAuth, getUsersChatSessions } from "@lib/firebase/firebase-server";

import ChatSidebarContent from "./chat-sidebar-content";

async function ChatSidebar() {
  const auth = await getAuth();

  let history;
  if (auth.session !== null) {
    history = await getUsersChatSessions(auth.session.uid);
  }

  return <ChatSidebarContent auth={auth} history={history} />;
}

export default ChatSidebar;
