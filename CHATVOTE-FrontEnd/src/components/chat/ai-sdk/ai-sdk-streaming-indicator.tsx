"use client";

import { Square } from "lucide-react";

type Props = {
  onStop?: () => void;
};

export default function AiSdkStreamingIndicator({ onStop }: Props) {
  return (
    <div className="flex items-center gap-3 px-4 py-2">
      <div className="flex items-center gap-1">
        <div className="bg-primary/60 size-1.5 animate-bounce rounded-full [animation-delay:-0.3s]" />
        <div className="bg-primary/60 size-1.5 animate-bounce rounded-full [animation-delay:-0.15s]" />
        <div className="bg-primary/60 size-1.5 animate-bounce rounded-full" />
      </div>
      {onStop && (
        <button
          type="button"
          onClick={onStop}
          className="text-muted-foreground hover:text-foreground flex items-center gap-1 rounded-full border border-white/10 px-2.5 py-0.5 text-xs transition-colors hover:bg-white/10"
        >
          <Square className="size-2.5" />
          Annuler
        </button>
      )}
    </div>
  );
}
