import { type NextPage } from "next";

import ChatView from "@components/chat/chat-view";

type ChatPageProps = {
  params: Promise<{
    chatId: string;
  }>;
  searchParams: Promise<{
    ref_snapshot_id: string;
    q: string;
    municipality_code?: string;
    mode?: string;
  }>;
};

const ChatPage: NextPage<ChatPageProps> = async ({ params, searchParams }) => {
  const { chatId } = await params;
  const { municipality_code } = await searchParams;

  return <ChatView sessionId={chatId} municipalityCode={municipality_code} />;
};

export default ChatPage;
