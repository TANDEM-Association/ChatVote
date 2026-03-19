"use client";

import { Sparkles, Users } from "lucide-react";

import { trackChatModeToggled } from "@lib/firebase/analytics";
import { cn } from "@lib/utils";
import { useChatModeStore } from "@lib/stores/chat-mode-store";

export function ChatModeToggle() {
  const { chatMode, setChatMode } = useChatModeStore();

  return (
    <div className="flex items-center rounded-lg border bg-muted p-0.5">
      <button
        className={cn(
          "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
          chatMode === "classic"
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground",
        )}
        title="Mode multi-parti — interrogez plusieurs partis simultanément"
        onClick={() => { setChatMode("classic"); trackChatModeToggled({ mode: "classic" }); }}
      >
        <Users className="mr-1 inline size-3.5" />
        Multi-parti
      </button>
      <button
        className={cn(
          "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
          chatMode === "ai-sdk"
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground",
        )}
        title="Assistant IA — conversation guidée avec un assistant intelligent"
        onClick={() => { setChatMode("ai-sdk"); trackChatModeToggled({ mode: "ai-sdk" }); }}
      >
        <Sparkles className="mr-1 inline size-3.5" />
        Assistant IA
      </button>
    </div>
  );
}
