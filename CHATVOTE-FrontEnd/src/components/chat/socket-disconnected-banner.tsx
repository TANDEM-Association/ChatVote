"use client";

import { useChatStore } from "@components/providers/chat-store-provider";
import { CircleAlertIcon } from "lucide-react";

function SocketDisconnectedBanner() {
  const isSocketConnected = useChatStore((state) => state.socket.connected);
  const isSessionInitialized = useChatStore(
    (state) => Boolean(state.chatId) && Boolean(state.municipalityCode),
  );

  return (
    <>
      {isSocketConnected === true && (
        <span data-testid="socket-connected" className="sr-only" />
      )}
      {isSessionInitialized && (
        <span data-testid="session-initialized" className="sr-only" />
      )}
      {isSocketConnected === false && (
        <div className="flex items-center justify-center bg-red-500 py-2 text-center text-xs text-white">
          <CircleAlertIcon className="mr-2 size-4" />
          Chat indisponible. Veuillez patienter ou actualiser la page.
        </div>
      )}
    </>
  );
}

export default SocketDisconnectedBanner;
