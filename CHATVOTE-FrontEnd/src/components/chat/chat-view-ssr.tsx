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
      // Session may not exist in Firestore yet (e.g. just created client-side
      // via Socket.IO). Return undefined so the client can proceed with its
      // in-memory Zustand state instead of redirecting away from the chat.
      console.warn(`Chat session ${chatId} not found in Firestore — proceeding with client state`);
      return undefined;
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
  // Fetch chat-specific data and independent data in parallel
  const [chatSession, messages] = chatId
    ? await Promise.all([
        getChatSessionServer(chatId, partyIds),
        getChatSessionMessages(chatId),
      ])
    : [undefined, undefined];

  const normalizedPartyIds = chatSession?.party_ids ?? partyIds;

  // Fetch parties and proposed questions in parallel (all independent)
  const [parties, allParties, proposedQuestions] = await Promise.all([
    normalizedPartyIds
      ? getPartiesById(normalizedPartyIds)
      : Promise.resolve(undefined),
    getParties(),
    getProposedQuestions(normalizedPartyIds),
  ]);

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
