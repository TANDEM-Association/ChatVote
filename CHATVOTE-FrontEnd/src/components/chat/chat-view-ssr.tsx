import { redirect } from "next/navigation";

import {
  getAuth,
  getChatSession,
  getChatSessionMessages,
  getParties,
  getPartiesById,
  getProposedQuestions,
} from "@lib/firebase/firebase-server";

import ChatMessagesView from "./chat-messages-view";

type Props = {
  chatId?: string;
  partyIds?: string[];
  initialQuestion?: string;
  municipalityCode?: string;
};

async function getChatSessionServer(chatId: string, partyIds?: string[]) {
  const inEmulator =
    process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true";

  if (!inEmulator) {
    const auth = await getAuth();

    if (!auth.session) {
      const searchParams = new URLSearchParams();
      partyIds?.forEach((partyId) => searchParams.append("party_id", partyId));
      redirect(`/chat?${searchParams.toString()}`);
    }
  }

  try {
    const session = await getChatSession(chatId);

    if (!session) {
      throw new Error("Chat session not found");
    }

    return session;
  } catch (error) {
    console.error("Error getting chat session", error);

    const searchParams = new URLSearchParams();
    partyIds?.forEach((partyId) => searchParams.append("party_id", partyId));

    redirect(`/chat?${searchParams.toString()}`);
  }
}

async function ChatViewSsr({
  chatId,
  partyIds,
  initialQuestion,
  municipalityCode,
}: Props) {
  const chatSession = chatId
    ? await getChatSessionServer(chatId, partyIds)
    : undefined;

  const messages = chatId ? await getChatSessionMessages(chatId) : undefined;

  const normalizedPartyIds = chatSession?.party_ids ?? partyIds;

  const parties = normalizedPartyIds
    ? await getPartiesById(normalizedPartyIds)
    : undefined;

  const allParties = await getParties();

  const proposedQuestions = await getProposedQuestions(normalizedPartyIds);

  return (
    <ChatMessagesView
      chatId={chatId}
      chatSession={chatSession}
      parties={parties}
      allParties={allParties}
      messages={messages}
      proposedQuestions={proposedQuestions}
      initialQuestion={initialQuestion}
      municipalityCode={municipalityCode}
    />
  );
}

export default ChatViewSsr;
