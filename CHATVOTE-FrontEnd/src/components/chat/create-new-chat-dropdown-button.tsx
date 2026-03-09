"use client";

import { useRouter } from "next/navigation";

import { useChatStore } from "@components/providers/chat-store-provider";

import CreateNewChatDropdownButtonTrigger from "./create-new-chat-dropdown-button-trigger";

function CreateNewChatDropdownButton() {
  const router = useRouter();
  const newChat = useChatStore((store) => store.newChat);

  const handleClick = () => {
    newChat();
    router.push("/chat");
  };

  return (
    <CreateNewChatDropdownButtonTrigger onTriggerClick={handleClick} />
  );
}

export default CreateNewChatDropdownButton;
