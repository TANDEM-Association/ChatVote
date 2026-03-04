import { useParams } from "next/navigation";

export function useChatParam(): string | undefined {
  const { chatId } = useParams();

  if (!chatId) return undefined;

  if (typeof chatId !== "string") throw new Error("Chat ID is not a string");

  return chatId;
}
