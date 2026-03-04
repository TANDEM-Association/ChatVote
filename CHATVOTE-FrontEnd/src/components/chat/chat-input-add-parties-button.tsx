import { PlusIcon } from "lucide-react";

import { useChatStore } from "../providers/chat-store-provider";

import ChatGroupPartySelect from "./chat-group-party-select";

type Props = {
  disabled: boolean;
};

function ChatInputAddPartiesButton({ disabled }: Props) {
  const partyIds = useChatStore((state) => state.partyIds);
  const setPartyIds = useChatStore((state) => state.setPartyIds);

  return (
    <div className="absolute top-2 left-2 z-40">
      <ChatGroupPartySelect
        selectedPartyIdsInStore={Array.from(partyIds)}
        onNewChat={(partyIds) => setPartyIds(partyIds)}
        addPartiesToChat
      >
        <button
          className="bg-primary text-primary-foreground z-40 flex shrink-0 items-center gap-1 rounded-full p-1 transition-all duration-200 ease-out enabled:hover:scale-95 disabled:cursor-not-allowed"
          disabled={disabled}
          type="button"
        >
          <PlusIcon className="size-4" />
        </button>
      </ChatGroupPartySelect>
    </div>
  );
}

export default ChatInputAddPartiesButton;
