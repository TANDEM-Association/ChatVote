<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/components/chat

## Purpose

The core UI layer for the chat feature — 63 components covering everything from the top-level chat view to individual streaming message chunks, party response cards, source references, pro/con expandables, voting behavior charts, and the sidebar. All real-time state comes from the Zustand `ChatStore` via `useChatStore()`.

## Key Files

| File                                        | Description                                                                                       |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `chat-view.tsx`                             | Top-level chat component (Server Component): renders sidebar, header, main content, and input bar |
| `chat-view-ssr.tsx`                         | SSR wrapper that hydrates the store with server-fetched session data                              |
| `chat-main-content.tsx`                     | Scrollable main content area with sidebar-aware layout                                            |
| `chat-messages-view.tsx`                    | Renders the list of `GroupedMessage` blocks                                                       |
| `chat-messages-scroll-view.tsx`             | Virtualized scroll container for messages                                                         |
| `chat-grouped-messages.tsx`                 | Renders a single grouped message (user + assistant responses per turn)                            |
| `chat-single-message.tsx`                   | Single assistant message card with streaming support                                              |
| `chat-single-streaming-message-content.tsx` | Renders content during streaming (partial text, thinking state)                                   |
| `chat-single-user-message.tsx`              | User message bubble                                                                               |
| `current-streaming-messages.tsx`            | Container for all in-flight streaming messages                                                    |
| `current-streaming-message.tsx`             | Single party's streaming message during a response cycle                                          |
| `chat-input.tsx`                            | Text input bar with party selection and submission                                                |
| `chat-dynamic-chat-input.tsx`               | Dynamic input that adapts to rate limit and system status                                         |
| `chat-header.tsx`                           | Top navigation bar with chat title and controls                                                   |
| `chat-empty-view.tsx`                       | Empty state shown before first message                                                            |
| `chat-party-header.tsx`                     | Party logo and name header above each response                                                    |
| `chat-message-reference.tsx`                | Source citation reference chip                                                                    |
| `chat-pro-con-button.tsx`                   | Button to trigger pro/con perspective generation                                                  |
| `chat-pro-con-expandable.tsx`               | Expandable panel showing pro/con perspective                                                      |
| `chat-voting-behavior-expandable.tsx`       | Expandable panel showing voting behavior data                                                     |
| `chat-voting-behavior-detail-view.tsx`      | Detailed voting record with Embla carousel                                                        |
| `overall-vote-chart.tsx`                    | Recharts chart of overall voting results                                                          |
| `parties-vote-chart.tsx`                    | Recharts chart of per-party voting results                                                        |
| `vote-chart.tsx`                            | Base vote chart component                                                                         |
| `chat-markdown.tsx`                         | Markdown renderer for assistant message content                                                   |
| `chat-message-like-dislike-buttons.tsx`     | Feedback buttons (like/dislike) on assistant messages                                             |
| `chat-scroll-down-indicator.tsx`            | Floating button to scroll to latest message                                                       |
| `socket-disconnected-banner.tsx`            | Banner shown when Socket.IO connection is lost                                                    |
| `ai-sdk/`                                   | AI SDK integration components (experimental)                                                      |
| `sidebar/`                                  | Chat sidebar: history, settings, party selector                                                   |
| `survey-banner.tsx`                         | Survey prompt banner shown after 8+ messages; tracks analytics events                             |
| `chat-group-party-select-content.tsx`       | Party selection content panel within group chat                                                   |
| `chat-group-party-select-submit-button.tsx` | Submit button for party selection in group chat                                                   |
| `chat-input-add-parties-button.tsx`         | Button to add more parties to the active session                                                  |
| `chat-input-rate-limit.tsx`                 | Rate limit warning display in the input area                                                      |
| `chat-input-gate.tsx`                       | Guards chat input based on municipality selection requirement                                     |
| `chat-postcode-prompt.tsx`                  | Prompts user to enter postcode for local scope                                                    |
| `chat-mode-toggle.tsx`                      | Toggle between national and local chat scope                                                      |
| `chat-view-switcher.tsx`                    | Switches between different chat view modes                                                        |
| `chat-action-button-highlight.tsx`          | Highlighted action button with animation                                                          |
| `chat-dislike-feedback-button.tsx`          | Dislike feedback button with reason collection                                                    |
| `chat-single-message-actions.tsx`           | Action bar (copy, like, dislike) on individual messages                                           |
| `chat-context-sidebar.tsx`                  | Contextual sidebar with session metadata                                                          |
| `chat-embed-header.tsx`                     | Header for embed/widget mode                                                                      |
| `chat-vote-charts-header.tsx`               | Header for voting behavior chart views                                                            |
| `chat-vote-details-header.tsx`              | Header for voting detail views                                                                    |
| `chat-vote-details-slide-counter.tsx`       | Slide counter for voting details carousel                                                         |
| `chat-voting-behavior-detail-button.tsx`    | Button to view detailed voting behavior                                                           |
| `chat-voting-behavior-detail-justification.tsx` | Justification text in voting detail view                                                      |
| `chat-voting-behavior-submitting-parties.tsx`   | Shows which parties are providing voting data                                                 |
| `chat-voting-behavior-summary-button.tsx`   | Button to generate voting behavior summary                                                        |
| `copy-button.tsx`                           | Copy-to-clipboard button for message content                                                      |
| `create-new-chat-dropdown-button.tsx`       | Dropdown button to create a new chat session                                                      |
| `create-new-chat-dropdown-button-trigger.tsx` | Trigger component for new chat dropdown                                                         |
| `demographic-bubble.tsx`                    | User demographics display bubble                                                                  |
| `dev-metadata-sidebar.tsx`                  | Developer metadata sidebar (debug info)                                                           |
| `dev-metadata-sidebar-wrapper.tsx`          | Wrapper for dev metadata sidebar                                                                  |
| `electoral-list-shared.tsx`                 | Shared electoral list display component                                                           |
| `group-chat-empty-view.tsx`                 | Empty state for group chat mode                                                                   |
| `initial-suggestion-bubble.tsx`             | Initial suggested question bubbles                                                                |
| `mini-dashboard-card.tsx`                   | Compact dashboard card for chat stats                                                             |
| `mobile-electoral-lists-bar.tsx`            | Mobile-optimized electoral lists bar                                                              |
| `pro-con-icon.tsx`                          | Icon component for pro/con indicators                                                             |
| `sponsor-partners.tsx`                      | Sponsor and partner logos display                                                                 |
| `thinking-message.tsx`                      | Animated placeholder during LLM response generation                                               |
| `animate-text-overflow.tsx`                 | Animated text truncation for long party names                                                     |
| `theme-mode-toggle.tsx`                     | Dark/light theme toggle button                                                                    |

## For AI Agents

### Working In This Directory

- All components here are Client Components (`"use client"`) except `chat-view.tsx` and `chat-view-ssr.tsx`.
- State is read from `useChatStore()` — never maintain local copies of chat state.
- Streaming state lives in `ChatStore.currentStreamingMessages`. A response cycle creates entries keyed by `session_id`, with per-party messages keyed by `party_id`.
- When adding a new Socket.IO event that updates UI, the event handler goes in `SocketProvider`, the store action goes in `src/lib/stores/actions/`, and the display component goes here.
- Embla Carousel is used for multi-party voting behavior details — use `chat-group-voting-behavior-embla-reinit.tsx` pattern for dynamic content.
- `chat-view.tsx` is a Server Component and calls Firebase server functions. Do not add client hooks to it.

### Testing Requirements

- `e2e/integration/streamed-responses.spec.ts` — streaming message flow
- `e2e/integration/source-attribution.spec.ts` — source chip rendering
- `e2e/integration/quick-replies.spec.ts` — quick reply suggestions
- `e2e/integration/chat-input.spec.ts` — input bar interactions

### Common Patterns

- Party response components receive `partyId` as prop and select their slice from the store.
- `message-loading-border-trail.tsx` wraps cards with an animated border during streaming.
- Pro/con and voting behavior features are triggered by user button clicks that emit Socket.IO events via store actions.
- Source references use `sources-button.tsx` to toggle a list of `chat-message-reference.tsx` chips.

## Dependencies

### Internal

- `@lib/stores/chat-store` — all real-time state
- `@lib/firebase/firebase-server` — session data (in `chat-view.tsx` only)
- `@lib/hooks/` — `useIsMounted`, `useCarouselCurrentIndex`
- `@components/ui/` — shadcn/ui primitives

### External

- `embla-carousel-react` — voting behavior carousel
- `recharts` — vote result charts
- `react-markdown` + `remark-gfm` — markdown rendering
- `motion` — message animations
- `lucide-react` — icons

<!-- MANUAL: -->
