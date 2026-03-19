<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# e2e

## Purpose

Playwright end-to-end test suite for the ChatVote frontend. Tests run against a real Next.js dev server with a Firebase emulator for Auth/Firestore and a mock Socket.IO server that replays pre-scripted streaming responses. Two Playwright configs exist: the default (`playwright.config.ts`) and the integration config (`playwright.integration.config.ts`).

## Key Files

| File                      | Description                                                         |
| ------------------------- | ------------------------------------------------------------------- |
| `global-setup.ts`         | Runs before all tests: starts Firebase emulator, seeds initial data |
| `global-teardown.ts`      | Runs after all tests: stops emulator, cleans up                     |
| `integration-setup.ts`    | Setup for integration suite: starts mock Socket.IO server           |
| `integration-teardown.ts` | Teardown for integration suite: stops mock server                   |

## Subdirectories

| Directory      | Purpose                                                  |
| -------------- | -------------------------------------------------------- |
| `integration/` | Integration test specs — one `.spec.ts` per feature area |
| `mock/`        | Mock Socket.IO server and support utilities              |
| `support/`     | Shared test helpers and fixtures                         |

### integration/ specs

| File                               | What it tests                                      |
| ---------------------------------- | -------------------------------------------------- |
| `authentication.spec.ts`           | Login, logout, anonymous auth, session persistence |
| `chat-input.spec.ts`               | Text input, submission, rate limit display         |
| `error-states.spec.ts`             | Socket disconnect banner, stream reset handling    |
| `guide-dialog.spec.ts`             | In-app guide dialog open/close                     |
| `landing-and-navigation.spec.ts`   | Home page, election flow, navigation               |
| `new-chat-party-selection.spec.ts` | Party selector in new chat                         |
| `persisted-sessions.spec.ts`       | Session restore from Firestore                     |
| `quick-replies.spec.ts`            | Quick reply chip rendering and click               |
| `responsive-layout.spec.ts`        | Mobile vs desktop layout                           |
| `sidebar.spec.ts`                  | Chat history sidebar open/close                    |
| `source-attribution.spec.ts`       | Source chip display on messages                    |
| `streamed-responses.spec.ts`       | Full streaming response flow end-to-end            |
| `theme-and-language.spec.ts`       | Dark/light theme toggle, FR/EN language switch     |

### mock/

| File                    | Description                                                                                                |
| ----------------------- | ---------------------------------------------------------------------------------------------------------- |
| `mock-socket-server.ts` | Socket.IO server that replays scripted party responses with streaming chunks, sources, and voting behavior |
| `start-mock-server.ts`  | Entry point to start the mock server as a separate process                                                 |
| `services.ts`           | Mock service helpers                                                                                       |
| `emulator-cleanup.ts`   | Firestore emulator cleanup between test runs                                                               |
| `test-helpers.ts`       | Shared Playwright page helpers and assertions                                                              |

## For AI Agents

### Working In This Directory

- Run integration tests with: `npx playwright test --config playwright.integration.config.ts`
- The mock Socket.IO server must be running during integration tests — `integration-setup.ts` starts it automatically.
- Firebase emulator must be running: `firebase emulators:start --only firestore,auth`
- Set `NEXT_PUBLIC_USE_FIREBASE_EMULATORS=true` in the test environment.
- `test-helpers.ts` contains reusable page actions (e.g., `sendMessage()`, `waitForStreamingComplete()`) — use these instead of repeating selectors.
- When adding a new spec, add it to `integration/` and follow the existing `test.describe` / `test.beforeEach` structure.
- The mock server in `mock-socket-server.ts` must be updated if new Socket.IO events are added to the backend protocol.

### Testing Requirements

```bash
# Run all integration tests
npx playwright test --config playwright.integration.config.ts

# Run a single spec
npx playwright test e2e/integration/streamed-responses.spec.ts --config playwright.integration.config.ts

# View test report
npx playwright show-report playwright-report
```

### Common Patterns

- Tests use `page.goto("/chat")` then interact via locators.
- Firebase emulator data is reset between suites via `reset-emulator.setup.ts`.
- Mock socket responses are deterministic — specific trigger messages map to scripted response sequences.

## Dependencies

### External

- `@playwright/test` — test runner, assertions, browser automation
- `socket.io` — used in `mock-socket-server.ts` (server-side)
- Firebase emulator — local Firestore and Auth

<!-- MANUAL: -->
