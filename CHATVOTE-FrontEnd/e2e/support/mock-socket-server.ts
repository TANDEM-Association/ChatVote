import { createServer } from 'node:http';
import { Server, type Socket } from 'socket.io';

const DELAY_MS = 200;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface ChatSessionInitPayload {
  session_id: string;
  party_ids?: string[];
  chat_history?: unknown[];
  current_title?: string;
  chat_response_llm_size?: string;
  last_quick_replies?: string[];
  scope?: string;
  municipality_code?: string;
  locale?: string;
}

interface ChatAnswerRequestPayload {
  session_id?: string;
  user_message?: string;
  party_ids?: string[];
  user_is_logged_in?: boolean;
}

interface ProConPerspectiveRequestPayload {
  request_id: string;
  party_id: string;
  last_assistant_message?: string;
  last_user_message?: string;
}

interface VotingBehaviorRequestPayload {
  request_id: string;
  party_id: string;
  last_user_message?: string;
  last_assistant_message?: string;
  summary_llm_size?: string;
  user_is_logged_in?: boolean;
}

export function startMockServer(port: number): Promise<{ close: () => Promise<void> }> {
  return new Promise((resolve, reject) => {
    // Return 404 for non-Socket.IO HTTP requests so SSR fetches
    // (e.g. fetchTopicStats in coverage-data.ts) resolve immediately
    // instead of hanging on a connection that never responds.
    const httpServer = createServer((req, res) => {
      if (!req.url?.startsWith('/socket.io')) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'not found (mock server)' }));
      }
    });
    const io = new Server(httpServer, {
      cors: {
        origin: '*',
        methods: ['GET', 'POST'],
      },
    });

    // Session state keyed by session_id (not socket.id) so that if the
    // client reconnects mid-flow (e.g. due to a locale-triggered socket
    // replacement), the chat_answer_request on the new socket can still
    // find the party_ids that were registered by chat_session_init.
    const sessionState = new Map<string, {
      party_ids: string[];
      scope?: string;
      municipality_code?: string;
    }>();
    // Reverse index: socket.id → session_ids it initialised, for cleanup.
    const socketSessions = new Map<string, string[]>();

    io.on('connection', (socket: Socket) => {
      console.log(`[MockServer] Client connected: ${socket.id}`);

      socket.on('chat_session_init', (payload: ChatSessionInitPayload) => {
        console.log(`[MockServer] chat_session_init`, payload);

        const session_id = payload.session_id ?? 'test-session';
        const existing = sessionState.get(session_id);
        if (existing) {
          // Accept re-init if scope or municipality changed (legitimate context switch).
          // Reject true duplicates (same scope/municipality) — these come from React
          // re-renders and would overwrite state.chatId during in-flight responses.
          const scopeChanged = payload.scope !== existing.scope
            || payload.municipality_code !== existing.municipality_code;
          if (!scopeChanged) {
            console.log(`[MockServer] duplicate init — reusing session ${session_id}`);
            if (payload.party_ids && payload.party_ids.length > 0) {
              existing.party_ids = payload.party_ids;
            }
            socket.emit('chat_session_initialized', { session_id });
            return;
          }
        }

        const party_ids: string[] =
          payload.party_ids && payload.party_ids.length > 0
            ? payload.party_ids
            : ['lfi', 'rn'];

        sessionState.set(session_id, {
          party_ids,
          scope: payload.scope,
          municipality_code: payload.municipality_code,
        });

        // Track which sessions this socket initialised (for disconnect cleanup).
        const sessions = socketSessions.get(socket.id) ?? [];
        sessions.push(session_id);
        socketSessions.set(socket.id, sessions);

        socket.emit('chat_session_initialized', { session_id });
      });

      socket.on('chat_answer_request', async (payload: ChatAnswerRequestPayload) => {
        console.log(`[MockServer] chat_answer_request`, payload);
        const session_id = payload.session_id ?? 'test-session';
        // Look up by session_id so the correct party_ids are used even when
        // chat_answer_request arrives on a different socket than chat_session_init
        // (which happens when the client replaces its socket mid-flow).
        const state = sessionState.get(session_id) ?? {
          party_ids: ['lfi', 'rn'],
        };
        const { party_ids } = state;

        await delay(DELAY_MS);

        // 1. responding_parties_selected
        socket.emit('responding_parties_selected', { session_id, party_ids });
        await delay(DELAY_MS);

        // 2. sources_ready for each party
        for (const party_id of party_ids) {
          socket.emit('sources_ready', {
            session_id,
            party_id,
            sources: [
              {
                title: 'Source Document',
                url: 'https://example.com/source',
                content: 'Relevant source content for testing.',
              },
            ],
            rag_query: 'test query',
          });
          await delay(DELAY_MS);
        }

        // 3. stream chunks for each party (3 content chunks + 1 end chunk)
        for (const party_id of party_ids) {
          for (let i = 0; i < 3; i++) {
            socket.emit('party_response_chunk_ready', {
              session_id,
              party_id,
              chunk_index: i,
              chunk_content: `Response chunk ${i}. `,
              is_end: false,
            });
            await delay(DELAY_MS);
          }
          // final chunk with is_end: true
          socket.emit('party_response_chunk_ready', {
            session_id,
            party_id,
            chunk_index: 3,
            chunk_content: '',
            is_end: true,
          });
          await delay(DELAY_MS);
        }

        // 4. party_response_complete for each party
        for (const party_id of party_ids) {
          socket.emit('party_response_complete', {
            session_id,
            party_id,
            complete_message: 'Response chunk 0. Response chunk 1. Response chunk 2. ',
          });
          await delay(DELAY_MS);
        }

        // 5. quick_replies_and_title_ready
        socket.emit('quick_replies_and_title_ready', {
          session_id,
          quick_replies: ['What about education?', 'Tell me about healthcare', 'Economic policies'],
          title: 'Test Chat Title',
        });
      });

      socket.on(
        'pro_con_perspective_request',
        async (payload: ProConPerspectiveRequestPayload) => {
          console.log(`[MockServer] pro_con_perspective_request`, payload);
          const { request_id } = payload;

          await delay(DELAY_MS);
          socket.emit('pro_con_perspective_complete', {
            request_id,
            message: {
              id: 'mock-procon-id',
              content: 'Pro: Good policy. Con: High cost.',
              sources: [],
              role: 'assistant',
              created_at: new Date().toISOString(),
            },
          });
        },
      );

      socket.on('voting_behavior_request', async (payload: VotingBehaviorRequestPayload) => {
        console.log(`[MockServer] voting_behavior_request`, payload);
        const { request_id } = payload;

        await delay(DELAY_MS);
        socket.emit('voting_behavior_complete', {
          request_id,
          votes: [],
          message: 'No voting records found for this topic.',
        });
      });

      socket.on('disconnect', () => {
        console.log(`[MockServer] Client disconnected: ${socket.id}`);
        const sessions = socketSessions.get(socket.id) ?? [];
        for (const session_id of sessions) {
          sessionState.delete(session_id);
        }
        socketSessions.delete(socket.id);
      });
    });

    httpServer.on('error', reject);

    httpServer.listen(port, () => {
      console.log(`[MockServer] Listening on :${port}`);
      resolve({
        close: () =>
          new Promise((res, rej) => {
            io.close((err: Error | undefined) => {
              if (err) rej(err);
              else res();
            });
          }),
      });
    });
  });
}
