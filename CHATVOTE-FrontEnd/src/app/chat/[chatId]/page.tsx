import { type NextPage } from "next";

import ChatView from "@components/chat/chat-view";

type ChatPageProps = {
  params: Promise<{
    chatId: string;
  }>;
  searchParams: Promise<{
    ref_snapshot_id: string;
    q: string;
  }>;
};

const ChatPage: NextPage<ChatPageProps> = async ({ params, searchParams }) => {
  const { chatId } = await params;
  const { q } = await searchParams;

  return <ChatView sessionId={chatId} initialQuestion={q} />;
};

export default ChatPage;
