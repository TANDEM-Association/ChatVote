---
name: debug-chat
description: Debug ChatVote chat errors using agent-browser in headed mode with full observability
---

# ChatVote Debug Pipeline

You are a debug agent for the ChatVote application. Use `agent-browser` CLI in **headed mode** to visually debug chat issues.

## Session Setup

The project has `agent-browser.json` configured with `headed: true` and session `chatvote-debug`.

## Debug Workflow

### Step 1: Open the chat page
```bash
agent-browser open "http://localhost:3000/chat/<CHAT_ID>" && agent-browser wait --load networkidle
```

### Step 2: Capture initial state
```bash
# Take annotated screenshot to see the UI
agent-browser screenshot --annotate /tmp/chatvote-debug-initial.png

# Get accessibility snapshot of interactive elements
agent-browser snapshot -i

# Check for any JS errors already present
agent-browser errors

# Check console logs
agent-browser console
```

### Step 3: Monitor network requests
```bash
# Clear and start monitoring network
agent-browser network requests --clear

# After performing an action:
agent-browser network requests --filter "socket.io"
agent-browser network requests --filter "api"
agent-browser network requests --filter "localhost:8080"
```

### Step 4: Inject debug logging via eval
```bash
# Intercept all Socket.IO events to log them
agent-browser eval "
(function() {
  if (window.__debugPatched) return 'Already patched';
  window.__debugPatched = true;
  window.__debugLogs = [];

  // Patch Socket.IO to log all events
  const origEmit = window.__socket?.emit;
  if (window.__socket) {
    const origOn = window.__socket.on.bind(window.__socket);
    const events = [
      'responding_parties_selected', 'sources_ready',
      'party_response_chunk_ready', 'quick_replies_and_title_ready',
      'chat_response_complete', 'error', 'connect_error'
    ];
    events.forEach(evt => {
      origOn(evt, (data) => {
        const log = {event: evt, data: JSON.stringify(data).slice(0,500), ts: Date.now()};
        window.__debugLogs.push(log);
        console.log('[DEBUG-SOCKETIO]', evt, data);
      });
    });
  }
  return 'Debug hooks installed';
})()
"
```

### Step 5: Read debug logs after interaction
```bash
# Read captured Socket.IO events
agent-browser eval "JSON.stringify(window.__debugLogs || [], null, 2)"

# Read console messages
agent-browser console

# Read JS errors
agent-browser errors

# Get network requests to backend
agent-browser network requests --filter "8080"
```

### Step 6: Check backend logs
```bash
# Tail backend logs for the relevant request
# Look for LLM queries, Qdrant searches, errors
make logs 2>&1 | tail -50
```

### Step 7: Take final screenshot
```bash
agent-browser screenshot --annotate /tmp/chatvote-debug-result.png
```

## What to Look For

### Frontend Issues
- Socket.IO connection errors (`connect_error`, `disconnect`)
- Missing or malformed event data
- React rendering errors in console
- Network requests returning 4xx/5xx

### Backend Issues (check backend terminal)
- LLM API errors (rate limits, auth failures)
- Qdrant query failures
- Prompt template errors
- Socket.IO event emission failures

### Data Flow Issues
- `chat_session_init` not completing
- `chat_answer_request` sent but no `responding_parties_selected` received
- `sources_ready` missing or empty sources
- `party_response_chunk_ready` chunks not arriving
- `chat_response_complete` never fired

## Reproducing a Bug
1. Open the chat URL in headed browser
2. Inject debug hooks (Step 4)
3. Clear network/console (`agent-browser network requests --clear && agent-browser console --clear`)
4. Perform the action that triggers the bug
5. Wait 5-10 seconds for async responses
6. Collect all evidence (Steps 5-6)
7. Screenshot the final state
