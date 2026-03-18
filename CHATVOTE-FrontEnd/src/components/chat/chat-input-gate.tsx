"use client";

import { useSearchParams } from "next/navigation";

type Props = {
  children: React.ReactNode;
  municipalityCode?: string;
};

/**
 * Hides the chat input until a municipality has been selected.
 * Reads `municipality_code` from the URL (set by ChatPostcodePrompt) or
 * falls back to the server-provided prop for direct URL access.
 */
export default function ChatInputGate({ children, municipalityCode }: Props) {
  const searchParams = useSearchParams();
  const hasCity = !!municipalityCode || !!searchParams.get("municipality_code");

  if (!hasCity) return null;

  return <>{children}</>;
}
