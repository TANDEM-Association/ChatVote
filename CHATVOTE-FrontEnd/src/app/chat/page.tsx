import { type NextPage } from "next";
import { redirect } from "next/navigation";

import ChatView from "@components/chat/chat-view";
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
    mode?: string;
  }>;
};
const ChatPage: NextPage<ChatPageProps> = async ({ searchParams }) => {
  const { chat_id, municipality_code, mode } = await searchParams;

  if (chat_id) {
    // Preserve query params (mode=ai, municipality_code) through the redirect
    const params = new URLSearchParams();
    if (mode) params.set('mode', mode);
    if (municipality_code) params.set('municipality_code', municipality_code);
    const qs = params.toString();
    redirect(`/chat/${chat_id}${qs ? `?${qs}` : ''}`);
  }

  return (
    <ChatView
      municipalityCode={municipality_code}
    />
  );
};

export default ChatPage;
