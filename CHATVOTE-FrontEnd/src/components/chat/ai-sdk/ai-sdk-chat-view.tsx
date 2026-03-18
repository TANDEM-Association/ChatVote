"use client";

import {
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import Image from "next/image";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { useChat } from "@ai-sdk/react";
import { MunicipalitySearch } from "@components/election-flow";
import {
  ChatStoreContext,
  useChatStore,
} from "@components/providers/chat-store-provider";
import { type Municipality } from "@lib/election/election.types";
import { auth as firebaseAuth } from "@lib/firebase/firebase";
import { useAiSdkFeaturesStore } from "@lib/stores/ai-sdk-features-store";
import { generateUuid } from "@lib/utils";
import { DefaultChatTransport, getToolName, isToolUIPart } from "ai";
import { Plus } from "lucide-react";

import SponsorPartners from "../sponsor-partners";

import AiSdkCandidateBar from "./ai-sdk-candidate-bar";
import AiSdkFeatureRibbon from "./ai-sdk-feature-ribbon";
import AiSdkMessage from "./ai-sdk-message";
import AiSdkStreamingIndicator from "./ai-sdk-streaming-indicator";

type Props = {
  chatId?: string;
  locale: string;
  municipalityCode?: string;
};

export default function AiSdkChatView({
  chatId,
  locale,
  municipalityCode: municipalityCodeProp,
}: Props) {
  const partyIds = useChatStore((s) => s.partyIds);
  const scope = useChatStore((s) => s.scope);
  const storeMunicipalityCode = useChatStore((s) => s.municipalityCode);
  const municipalityCode = municipalityCodeProp ?? storeMunicipalityCode;
  const getEnabledFeatureIds = useAiSdkFeaturesStore(
    (s) => s.getEnabledFeatureIds,
  );
  const setPartyIds = useChatStore((s) => s.setPartyIds);
  const storeApi = useContext(ChatStoreContext);

  // Sync store from URL prop on mount (e.g. /chat?municipality_code=69123)
  useEffect(() => {
    if (municipalityCodeProp && storeApi) {
      const { municipalityCode: current, scope: currentScope } =
        storeApi.getState();
      if (current !== municipalityCodeProp || currentScope !== "local") {
        storeApi.setState({
          municipalityCode: municipalityCodeProp,
          scope: "local",
        });
      }
    }
  }, [municipalityCodeProp, storeApi]);

  // Municipality search
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [selectedMunicipality, setSelectedMunicipality] =
    useState<Municipality | null>(null);

  const handleSelectMunicipality = useCallback(
    (municipality: Municipality) => {
      setSelectedMunicipality(municipality);
      // Update store so municipalityCode changes immediately (candidate bar appears)
      if (storeApi) {
        storeApi.setState({
          municipalityCode: municipality.code,
          scope: "local",
        });
      }
      const next = new URLSearchParams(searchParams.toString());
      next.set("municipality_code", municipality.code);
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams, storeApi],
  );

  // Stabilize partyIds — only update ref when the actual values change
  const partyIdsRef = useRef<string[]>([]);
  const currentIds = Array.from(partyIds).sort().join(",");
  const prevIds = partyIdsRef.current.sort().join(",");
  if (currentIds !== prevIds) {
    partyIdsRef.current = Array.from(partyIds);
  }

  const [input, setInput] = useState("");

  // Generate a stable chat ID for this session
  const aiChatIdRef = useRef<string>(chatId ?? "");

  // Keep a ref with the latest body values so the memoized transport
  // always sends fresh data (Resolvable<object> accepts a function).
  const bodyRef = useRef({
    partyIds: partyIdsRef.current,
    locale,
    chatId: aiChatIdRef.current || chatId,
    scope,
    municipalityCode,
    enabledFeatures: getEnabledFeatureIds(),
  });
  bodyRef.current = {
    partyIds: partyIdsRef.current,
    locale,
    chatId: aiChatIdRef.current || chatId,
    scope,
    municipalityCode,
    enabledFeatures: getEnabledFeatureIds(),
  };

  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: "/api/ai-chat",
        body: () => bodyRef.current,
        headers: async (): Promise<Record<string, string>> => {
          const token = await firebaseAuth.currentUser?.getIdToken();
          return token ? { Authorization: `Bearer ${token}` } : {};
        },
      }),

    [],
  );

  const { messages, sendMessage, regenerate, stop, status, error } = useChat({
    transport,
  });

  // Apply context tool results to the store when messages arrive
  useEffect(() => {
    for (const message of messages) {
      if (message.role !== "assistant") continue;
      for (const part of message.parts) {
        if (!isToolUIPart(part) || part.state !== "output-available") continue;
        const toolName = getToolName(part);

        if (toolName === "changeCity") {
          const result = part.output as {
            municipalityCode?: string;
            cityName?: string;
          };
          if (result.municipalityCode && storeApi) {
            storeApi.setState({
              municipalityCode: result.municipalityCode,
              scope: "local",
            });
            // Update URL so the prop also changes (no reload)
            const next = new URLSearchParams(searchParams.toString());
            next.set("municipality_code", result.municipalityCode);
            router.replace(`${pathname}?${next.toString()}`, { scroll: false });
          }
        } else if (toolName === "changeCandidates") {
          const result = part.output as {
            partyIds: string[];
            operation: string;
          };
          if (result.operation === "set") {
            setPartyIds(result.partyIds);
          } else if (result.operation === "add") {
            const current = Array.from(storeApi?.getState().partyIds ?? []);
            setPartyIds([...new Set([...current, ...result.partyIds])]);
          } else if (result.operation === "remove") {
            const current = Array.from(storeApi?.getState().partyIds ?? []);
            setPartyIds(current.filter((id) => !result.partyIds.includes(id)));
          }
        } else if (toolName === "removeRestrictions") {
          if (storeApi) {
            storeApi.setState({
              municipalityCode: undefined,
              scope: "national",
            });
          }
          setPartyIds([]);
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // Ensure a chat ID is generated for this session and update the URL.
  // Uses window.history.replaceState — the official Next.js App Router approach
  // for shallow URL updates (no server round-trip, no component remount).
  const ensureChatId = useCallback(() => {
    if (!aiChatIdRef.current) {
      const newChatId = generateUuid();
      aiChatIdRef.current = newChatId;
      const params = new URLSearchParams(window.location.search);
      params.set("chat_id", newChatId);
      window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
    }
  }, []);

  // Wrapper that ensures chat ID before sending (used by suggestions & follow-ups)
  const handleSendMessage = useCallback(
    (text: string) => {
      if (!text.trim() || status === "streaming") return;
      ensureChatId();
      sendMessage({ text });
    },
    [ensureChatId, sendMessage, status],
  );

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || status === "streaming") return;
    ensureChatId();
    sendMessage({ text });
    setInput("");
  };

  // Dev-only UI invariant guards
  useEffect(() => {
    if (process.env.NODE_ENV !== "development") return;
    const timer = setTimeout(() => {
      const hasCandidateSelector = !!document.querySelector(
        '[data-testid="candidate-selector"]',
      );
      const hasMunicipalitySearch = !!document.querySelector(
        '[data-testid="municipality-search"]',
      );
      const hasSuggestions = !!document.querySelector(
        '[data-testid="quick-suggestions"]',
      );

      // Rule 1: If municipality is set, candidate selector MUST be visible
      if (municipalityCode && !hasCandidateSelector) {
        console.error(
          "[UI Guard] Municipality is set but candidate-selector is NOT visible",
        );
      }
      // Rule 2: If no municipality, municipality search MUST be visible (when no messages)
      if (
        !municipalityCode &&
        messages.length === 0 &&
        !hasMunicipalitySearch
      ) {
        console.error(
          "[UI Guard] No municipality set but municipality-search is NOT visible",
        );
      }
      // Rule 3: municipality-search and candidate-selector are mutually exclusive
      if (hasCandidateSelector && hasMunicipalitySearch) {
        console.error(
          "[UI Guard] Both candidate-selector AND municipality-search are visible",
        );
      }
      // Rule 4: Quick suggestions only visible when municipality is set and no messages
      if (municipalityCode && messages.length === 0 && !hasSuggestions) {
        console.warn(
          "[UI Guard] Municipality set with no messages but quick-suggestions not visible",
        );
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [municipalityCode, messages.length]);

  // ── Sticky auto-scroll ──────────────────────────────────────────────────
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  // Track whether the user has scrolled away from bottom
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const threshold = 40;
      isAtBottomRef.current =
        el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Auto-scroll to bottom when new content arrives (messages or streaming)
  useLayoutEffect(() => {
    if (isAtBottomRef.current) {
      bottomRef.current?.scrollIntoView({ block: "end" });
    }
  }, [messages, status]);

  return (
    <div className="flex h-full flex-col">
      {/* Feature toggle ribbon */}
      <AiSdkFeatureRibbon />

      {/* Candidate/party pills — always selectable */}
      {municipalityCode && (
        <div data-testid="candidate-selector">
          <AiSdkCandidateBar
            municipalityCode={municipalityCode}
            selectable
            onSelectionChange={(ids) => setPartyIds(ids)}
          />
        </div>
      )}

      {messages.length > 0 && (
        <div className="flex justify-end px-3 py-1.5 md:px-9">
          <button
            onClick={() => window.location.reload()}
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs transition-colors hover:border-white/20 hover:bg-white/10"
          >
            <Plus className="size-3" />
            Nouveau chat
          </button>
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-4 md:px-9">
        <div className="mx-auto max-w-3xl space-y-6">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-5 py-8">
              <Image
                src="/images/logos/chatvote.svg"
                alt="ChatVote"
                width={260}
                height={87}
                priority
              />

              <p className="text-muted-foreground text-center text-sm">
                {municipalityCode
                  ? "Sélectionnez les candidats ci-dessus puis posez une question"
                  : "Avant de poser votre question, renseignez votre commune ou code postal"}
              </p>

              {!municipalityCode && (
                <div
                  className="mx-auto w-full max-w-md"
                  data-testid="municipality-search"
                >
                  <MunicipalitySearch
                    selectedMunicipality={selectedMunicipality}
                    onSelectMunicipality={handleSelectMunicipality}
                    municipalityCode={undefined}
                  />
                </div>
              )}

              {municipalityCode && (
                <div
                  className="mt-2 flex flex-wrap justify-center gap-2"
                  data-testid="quick-suggestions"
                >
                  {[
                    "Que proposent les candidats sur la sécurité ?",
                    "Quelles sont les positions sur l'écologie ?",
                    "Comment améliorer l'éducation dans ma commune ?",
                    "Que disent les candidats sur le pouvoir d'achat ?",
                  ].map((q) => (
                    <button
                      key={q}
                      onClick={() => handleSendMessage(q)}
                      className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs transition-colors hover:bg-white/10"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}

              <SponsorPartners />
            </div>
          )}

          {messages.map((message) => (
            <AiSdkMessage
              key={message.id}
              message={message}
              onSendMessage={handleSendMessage}
            />
          ))}

          {status === "streaming" && <AiSdkStreamingIndicator onStop={stop} />}

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950">
              <p className="text-sm text-red-800 dark:text-red-200">
                Une erreur est survenue.
                <button
                  onClick={() => regenerate()}
                  className="ml-2 font-medium underline hover:no-underline"
                >
                  Réessayer
                </button>
              </p>
              {process.env.NODE_ENV === "development" && (
                <pre className="mt-2 max-h-24 overflow-auto text-xs text-red-600 opacity-70 dark:text-red-400">
                  {error.message}
                </pre>
              )}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="px-3 py-3 md:px-9">
        <form
          onSubmit={handleSubmit}
          className="relative mx-auto flex max-w-3xl items-center gap-4 overflow-hidden rounded-4xl border border-white/10 bg-white/5 px-4 py-3 transition-colors focus-within:border-white/20"
        >
          <input
            className="placeholder:text-muted-foreground flex-1 text-base whitespace-pre focus-visible:ring-0 focus-visible:outline-none disabled:cursor-not-allowed"
            placeholder="Posez une question..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={status === "streaming"}
          />
          {status === "streaming" ? (
            <button
              type="button"
              onClick={stop}
              className="bg-foreground text-background hover:bg-foreground/80 flex size-8 flex-none items-center justify-center rounded-full transition-colors"
            >
              <span className="size-3 rounded-sm bg-current" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.length}
              className="bg-foreground text-background hover:bg-foreground/80 disabled:bg-foreground/20 disabled:text-muted flex size-8 flex-none items-center justify-center rounded-full transition-colors"
            >
              <svg
                className="size-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 19V5M5 12l7-7 7 7" />
              </svg>
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
