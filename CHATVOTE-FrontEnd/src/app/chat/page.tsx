import { type NextPage } from "next";
import { redirect } from "next/navigation";

import ChatView from "@components/chat/chat-view";
import { getParties } from "@lib/firebase/firebase-server";
import { generateOgImageUrl } from "@lib/utils";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<{
    party_id: string[];
    q?: string;
  }>;
}) {
  const { party_id } = await searchParams;

  if (
    !party_id ||
    (Array.isArray(party_id) && (party_id.length === 0 || party_id.length > 1))
  ) {
    return;
  }

  const partyId = Array.isArray(party_id) ? party_id[0] : party_id;

  return {
    openGraph: {
      images: [await generateOgImageUrl(partyId)],
    },
  };
}

type ChatPageProps = {
  searchParams: Promise<{
    chat_id?: string;
    party_id: string[] | string | undefined;
    q?: string;
    municipality_code?: string;
  }>;
};
const ChatPage: NextPage<ChatPageProps> = async ({ searchParams }) => {
  const { party_id, q, chat_id, municipality_code } = await searchParams;
  const parties = await getParties();

  if (chat_id) {
    redirect(`/chat/${chat_id}`);
  }

  let normalizedPartyIds = Array.isArray(party_id)
    ? party_id
    : party_id
      ? [party_id]
      : undefined;

  normalizedPartyIds = normalizedPartyIds?.filter((id) =>
    parties.some((p) => p.party_id === id),
  );

  return (
    <ChatView
      partyIds={normalizedPartyIds}
      initialQuestion={q}
      municipalityCode={municipality_code}
    />
  );
};

export default ChatPage;
