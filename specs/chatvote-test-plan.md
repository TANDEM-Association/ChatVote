# ChatVote E2E Test Plan

## Application Overview

ChatVote is a French political information chatbot where citizens can ask questions to multiple political parties simultaneously and receive AI-generated, source-backed answers via RAG (Retrieval-Augmented Generation). The frontend is built with Next.js 16, Tailwind CSS, Zustand state management, Socket.IO for real-time streaming, and Firebase Auth (email, Google, Microsoft, anonymous). The backend is a Python aiohttp + Socket.IO server. Tests use a mock Socket.IO server running on port 8080 and Firebase emulators for auth and Firestore. The app is served at http://localhost:3000.

Key user flows:
1. User lands on the app, is redirected to /chat
2. User selects a municipality (commune) to unlock the chat input
3. User optionally selects one or more political parties to chat with
4. User types a question and receives streamed, source-backed answers from each selected party
5. User can explore pro/con perspectives and voting behavior summaries for each answer
6. User can like/dislike and copy answers, click quick reply suggestions
7. User can log in (email, Google, Microsoft) to persist conversations
8. User can switch language (FR/EN) and theme (light/dark)
9. Sidebar provides navigation to guide, legal notice, privacy policy, donate, and feedback pages

## Test Scenarios

### 1. Landing Page and Navigation

**Seed:** `seed.spec.ts`

#### 1.1. Root URL redirects to /chat

**File:** `tests/landing-and-navigation/root-redirect.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/
    - expect: The browser URL changes to match /chat within a few seconds
    - expect: The /chat page content is visible (logo, municipality input)

#### 1.2. /chat page displays the ChatVote logo and municipality search input

**File:** `tests/landing-and-navigation/chat-page-initial-state.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat
    - expect: The chatvote logo image is visible
    - expect: The municipality search input (placeholder matching 'commune' or 'municipality') is visible
    - expect: The chat text input is disabled (cannot type a message yet)

#### 1.3. Header elements are present on the chat page

**File:** `tests/landing-and-navigation/header-elements.spec.ts`

**Steps:**
  1. Navigate to /chat and wait for the page to fully load
    - expect: The theme toggle button is visible in the header
    - expect: The language switcher combobox is visible in the header
    - expect: The help (HowTo) icon button is visible
    - expect: The 'Create new chat' dropdown button is visible

#### 1.4. Guide page loads at /guide

**File:** `tests/landing-and-navigation/guide-page.spec.ts`

**Steps:**
  1. Navigate directly to http://localhost:3000/guide
    - expect: The page URL is /guide
    - expect: The guide page content is rendered without errors

#### 1.5. Legal notice page loads at /legal-notice

**File:** `tests/landing-and-navigation/legal-notice-page.spec.ts`

**Steps:**
  1. Navigate directly to http://localhost:3000/legal-notice
    - expect: The page URL is /legal-notice
    - expect: The legal notice page content is rendered without errors

#### 1.6. Privacy policy page loads at /privacy-policy

**File:** `tests/landing-and-navigation/privacy-policy-page.spec.ts`

**Steps:**
  1. Navigate directly to http://localhost:3000/privacy-policy
    - expect: The page URL is /privacy-policy
    - expect: The privacy policy page content is rendered without errors

#### 1.7. Donate page loads at /donate

**File:** `tests/landing-and-navigation/donate-page.spec.ts`

**Steps:**
  1. Navigate directly to http://localhost:3000/donate
    - expect: The page URL is /donate
    - expect: The donate page content is rendered without errors

#### 1.8. Navigating to a non-existent chat session ID shows an error or redirects

**File:** `tests/landing-and-navigation/invalid-chat-session.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat/nonexistent-chat-id-12345
    - expect: The app does not crash
    - expect: Either a 404/error page is shown, or the user is redirected to /chat

#### 1.9. Direct navigation to /chat with chat_id query param redirects to /chat/:chatId

**File:** `tests/landing-and-navigation/chat-id-redirect.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat?chat_id=some-test-id
    - expect: The browser URL changes to /chat/some-test-id

### 2. Sidebar Navigation

**Seed:** `seed.spec.ts`

#### 2.1. Sidebar shows navigation links on desktop

**File:** `tests/sidebar/sidebar-desktop-links.spec.ts`

**Steps:**
  1. Set viewport to 1280x800 and navigate to /chat
    - expect: The 'How does chatvote work?' link is visible and points to /guide
    - expect: The 'Legal notice' link is visible
    - expect: The 'Privacy' link is visible

#### 2.2. Sidebar shows support action buttons on desktop

**File:** `tests/sidebar/sidebar-action-buttons.spec.ts`

**Steps:**
  1. Set viewport to 1280x800 and navigate to /chat
    - expect: The 'Log in' button is visible in the sidebar
    - expect: The 'Donate' button is visible in the sidebar
    - expect: The 'Feedback' button is visible in the sidebar

#### 2.3. Sidebar can be toggled open and closed

**File:** `tests/sidebar/sidebar-toggle.spec.ts`

**Steps:**
  1. Navigate to /chat on desktop viewport (1280x800)
    - expect: The sidebar content including legal notice link is visible
  2. Click the sidebar toggle button
    - expect: The sidebar collapses and its navigation links are no longer visible
  3. Click the sidebar toggle button again
    - expect: The sidebar expands and the navigation links become visible again

#### 2.4. Sidebar Guide link navigates to /guide

**File:** `tests/sidebar/sidebar-guide-link.spec.ts`

**Steps:**
  1. Navigate to /chat on desktop viewport
    - expect: Sidebar is visible
  2. Click the 'How does chatvote work?' link in the sidebar
    - expect: The browser navigates to /guide
    - expect: The guide page content is rendered

#### 2.5. Sidebar Donate button navigates to /donate

**File:** `tests/sidebar/sidebar-donate-button.spec.ts`

**Steps:**
  1. Navigate to /chat on desktop viewport
    - expect: The Donate button is visible in the sidebar
  2. Click the 'Donate' button
    - expect: The browser navigates to /donate or a donation flow is initiated

### 3. Municipality Selection

**Seed:** `seed.spec.ts`

#### 3.1. Municipality search input is visible on the empty chat page

**File:** `tests/municipality/municipality-input-visible.spec.ts`

**Steps:**
  1. Navigate to /chat
    - expect: The municipality search input with placeholder matching 'commune' or 'municipality' is visible
    - expect: The chat text input is disabled

#### 3.2. Typing in the municipality input shows autocomplete suggestions

**File:** `tests/municipality/municipality-autocomplete.spec.ts`

**Steps:**
  1. Navigate to /chat
    - expect: The municipality search input is visible
  2. Type 'Paris' into the municipality search input with a small delay between characters
    - expect: A dropdown list of municipality suggestions appears
    - expect: At least one suggestion matching 'Paris' is visible as a list item with a button

#### 3.3. Selecting a municipality from autocomplete updates the URL and enables the chat input

**File:** `tests/municipality/municipality-selection-enables-chat.spec.ts`

**Steps:**
  1. Navigate to /chat
    - expect: The municipality search input is visible
  2. Type 'Paris' into the municipality search input
    - expect: Autocomplete suggestions appear
  3. Click the first suggestion button in the autocomplete list
    - expect: The URL updates to include municipality_code= as a query parameter
    - expect: The chat text input becomes enabled

#### 3.4. Selecting Lyon as municipality works correctly

**File:** `tests/municipality/municipality-selection-lyon.spec.ts`

**Steps:**
  1. Navigate to /chat
    - expect: The municipality search input is visible
  2. Type 'Lyon' into the municipality search input
    - expect: Autocomplete suggestions appear with Lyon
  3. Click the Lyon suggestion
    - expect: The URL contains municipality_code corresponding to Lyon
    - expect: The chat input is enabled

#### 3.5. Municipality selection persists when navigating back to the page

**File:** `tests/municipality/municipality-selection-persists.spec.ts`

**Steps:**
  1. Navigate to /chat, select Paris as municipality
    - expect: The URL contains municipality_code=75056 and the chat input is enabled
  2. Navigate to /guide then click the browser back button
    - expect: The browser returns to /chat
    - expect: The municipality code is retained in the URL or the input shows the previously selected municipality

#### 3.6. Typing a non-existent municipality shows no results

**File:** `tests/municipality/municipality-no-results.spec.ts`

**Steps:**
  1. Navigate to /chat
    - expect: The municipality search input is visible
  2. Type 'xyznonexistentcommune999' into the municipality search input
    - expect: Either no autocomplete suggestions appear, or an empty/no-results state is shown
    - expect: The chat input remains disabled

### 4. Chat Input and Message Submission

**Seed:** `seed.spec.ts`

#### 4.1. Chat input is disabled before municipality selection

**File:** `tests/chat-input/input-disabled-before-municipality.spec.ts`

**Steps:**
  1. Navigate to /chat without selecting a municipality
    - expect: The chat text input (placeholder matching 'write a message' or 'crivez un message') is in a disabled state and cannot be interacted with

#### 4.2. Chat input becomes enabled after municipality selection

**File:** `tests/chat-input/input-enabled-after-municipality.spec.ts`

**Steps:**
  1. Navigate to /chat and select 'Paris' as the municipality
    - expect: The chat text input is now enabled and can receive keyboard input

#### 4.3. Pressing Enter submits the message

**File:** `tests/chat-input/submit-with-enter.spec.ts`

**Steps:**
  1. Navigate to /chat and select a municipality to enable the input
    - expect: The chat input is enabled
  2. Type 'What is your education policy?' into the chat input
    - expect: The text appears in the input field
  3. Press the Enter key
    - expect: The user message 'What is your education policy?' appears in the chat conversation
    - expect: The chat input is cleared

#### 4.4. Clicking the send (ArrowUp) button submits the message

**File:** `tests/chat-input/submit-with-button.spec.ts`

**Steps:**
  1. Navigate to /chat and select a municipality
    - expect: The chat input is enabled
  2. Type 'Tell me about healthcare' into the chat input
    - expect: The submit button (with ArrowUp icon) becomes active/enabled
  3. Click the send button
    - expect: The user message appears in the conversation
    - expect: The input is cleared

#### 4.5. Empty input does not submit a message

**File:** `tests/chat-input/empty-input-no-submit.spec.ts`

**Steps:**
  1. Navigate to /chat and select a municipality
    - expect: The chat input is enabled and empty
  2. Press the Enter key without typing anything
    - expect: No message is sent
    - expect: The URL does not acquire a chat_id parameter
    - expect: The conversation area remains unchanged

#### 4.6. Whitespace-only input does not submit a message

**File:** `tests/chat-input/whitespace-input-no-submit.spec.ts`

**Steps:**
  1. Navigate to /chat and select a municipality
    - expect: The chat input is enabled
  2. Type multiple spaces into the chat input and press Enter
    - expect: No message is sent
    - expect: No chat_id appears in the URL

#### 4.7. Send button is disabled when input is empty

**File:** `tests/chat-input/send-button-disabled-when-empty.spec.ts`

**Steps:**
  1. Navigate to /chat and select a municipality
    - expect: The chat input is enabled and empty
  2. Observe the send (ArrowUp) button without typing
    - expect: The send button is in a disabled state
  3. Type any character into the input
    - expect: The send button becomes enabled

#### 4.8. Chat input is disabled while a response is streaming

**File:** `tests/chat-input/input-disabled-during-streaming.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, and send a message
    - expect: The user message appears in the conversation
  2. Immediately observe the chat input and send button while streaming is in progress
    - expect: The chat input is disabled during the streaming response
    - expect: The send button is disabled
    - expect: A loading animation or border trail is visible on the input form

#### 4.9. AI disclaimer text is visible below the chat input

**File:** `tests/chat-input/ai-disclaimer-visible.spec.ts`

**Steps:**
  1. Navigate to /chat and select a municipality
    - expect: Text matching 'chatvote can make mistakes' or 'chatvote peut faire des erreurs' is visible below the chat input area

#### 4.10. Learn more button next to disclaimer is visible and clickable

**File:** `tests/chat-input/learn-more-button.spec.ts`

**Steps:**
  1. Navigate to /chat and select a municipality
    - expect: A button or link matching 'learn more here' or 'en savoir plus' is visible near the disclaimer text
  2. Click the 'learn more' button
    - expect: A dialog opens explaining the chatbot's limitations, or the user is navigated to the guide page

### 5. Party Selection

**Seed:** `seed.spec.ts`

#### 5.1. 'Comparer les partis' button is visible on the empty chat page

**File:** `tests/party-selection/compare-button-visible.spec.ts`

**Steps:**
  1. Navigate to /chat
    - expect: A button with text matching 'Comparer les partis' (or English equivalent) is visible on the page

#### 5.2. Clicking 'Comparer les partis' opens the party selection modal

**File:** `tests/party-selection/compare-button-opens-modal.spec.ts`

**Steps:**
  1. Navigate to /chat
    - expect: The 'Comparer les partis' button is visible
  2. Click the 'Comparer les partis' button
    - expect: A modal dialog opens with a heading matching 'Party selection' or 'Sélection des partis'
    - expect: A list of available political parties is displayed with checkboxes or toggle buttons

#### 5.3. User can select one party in the modal and start a chat

**File:** `tests/party-selection/single-party-selection.spec.ts`

**Steps:**
  1. Navigate to /chat and click 'Comparer les partis' to open the modal
    - expect: The party selection modal is open
  2. Click on one political party to select it
    - expect: The party appears selected (highlighted or checked)
  3. Click the submit/confirm button to start the chat
    - expect: The modal closes
    - expect: The chat view updates to show the selected party's identity (logo/name)
    - expect: The URL updates with party_id= query parameter

#### 5.4. User can select multiple parties for a group chat

**File:** `tests/party-selection/multi-party-selection.spec.ts`

**Steps:**
  1. Navigate to /chat and click 'Comparer les partis' to open the modal
    - expect: The party selection modal is open
  2. Click on three different political parties to select them
    - expect: All three parties appear selected
    - expect: The party count or selected count indicator updates
  3. Click the submit/confirm button
    - expect: The modal closes
    - expect: The group chat empty view is shown with all three party logos/identifiers visible
    - expect: Multiple party_id= parameters appear in the URL

#### 5.5. Closing the party selection modal without confirming makes no changes

**File:** `tests/party-selection/modal-cancel.spec.ts`

**Steps:**
  1. Navigate to /chat and open the party selection modal
    - expect: The modal is open
  2. Select one or more parties, then click the close/cancel button or press Escape
    - expect: The modal closes
    - expect: The chat view remains unchanged
    - expect: No party_id parameters are added to the URL

#### 5.6. Party pre-selection via URL query parameter works

**File:** `tests/party-selection/url-party-preselection.spec.ts`

**Steps:**
  1. Navigate to /chat?party_id=<valid_party_id> (using a party ID that exists in Firestore seed data)
    - expect: The chat view shows the selected party's empty state (logo and description)
    - expect: The party is pre-selected without any user interaction

#### 5.7. User can add more parties to an existing chat via the add parties button

**File:** `tests/party-selection/add-parties-to-existing-chat.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, select one party and send a message so quick replies appear
    - expect: The quick replies and an 'add parties' button are visible in the chat input area
  2. Click the add parties button in the chat input area
    - expect: The party selection modal opens in 'modify parties' mode
    - expect: The description text matches 'Modify parties' or 'Modifier les partis'
  3. Select an additional party and confirm
    - expect: The modal closes and the new party is added to the conversation

### 6. Streamed Responses

**Seed:** `seed.spec.ts`

#### 6.1. Submitting a question shows streamed response chunks appearing progressively

**File:** `tests/streamed-responses/streaming-chunks-appear.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, and send the message 'What is your education policy?'
    - expect: The user message appears in the conversation
  2. Wait and observe the response area
    - expect: Response text begins appearing progressively (streaming chunks visible, e.g. 'Response chunk')
    - expect: A loading/streaming indicator is visible on the chat input during streaming

#### 6.2. Full response text is displayed after streaming completes

**File:** `tests/streamed-responses/complete-response-text.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, send a message, and wait for streaming to finish
    - expect: The complete response text from the mock server is visible in the chat
    - expect: The loading state is cleared from the chat input

#### 6.3. Multiple party responses are shown in a group chat

**File:** `tests/streamed-responses/multiple-party-responses.spec.ts`

**Steps:**
  1. Navigate to /chat with multiple parties selected, select a municipality, and send a question
    - expect: Each selected party's response appears as a separate message or panel in the conversation
    - expect: Each response panel shows the party's identifying information (name or logo)

#### 6.4. Socket disconnected banner appears when connection is lost

**File:** `tests/streamed-responses/socket-disconnected-banner.spec.ts`

**Steps:**
  1. Navigate to /chat and simulate a Socket.IO disconnection (e.g., disable network or stop the mock server)
    - expect: A 'Socket disconnected' warning banner appears below the header
    - expect: The chat input may be disabled or a reconnect prompt is shown

### 7. Quick Reply Suggestions

**Seed:** `seed.spec.ts`

#### 7.1. Quick replies appear above the chat input after a response completes

**File:** `tests/quick-replies/quick-replies-appear.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, and send the message 'Education policy?'
    - expect: The user message appears and a response streams in
  2. Wait for the response to complete
    - expect: Quick reply suggestion buttons appear above the chat input
    - expect: Buttons with text matching 'What about education', 'Tell me about healthcare', and 'Economic policies' are visible (from mock server)

#### 7.2. Clicking a quick reply sends it as a new message

**File:** `tests/quick-replies/quick-reply-click-sends-message.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, send a message, and wait for quick replies to appear
    - expect: Quick reply buttons are visible
  2. Click the 'What about education' quick reply button
    - expect: The quick reply text is sent as a new user message
    - expect: A new response streaming cycle begins
    - expect: The quick reply buttons disappear during the new streaming session

#### 7.3. Quick reply buttons are scrollable horizontally if they overflow

**File:** `tests/quick-replies/quick-replies-horizontal-scroll.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, send a message, and wait for several quick replies to appear on a narrow viewport (e.g., 375px width)
    - expect: The quick reply buttons are arranged in a horizontal scrollable row
    - expect: No vertical overflow or line wrapping occurs in the quick reply container

### 8. Source Attribution

**Seed:** `seed.spec.ts`

#### 8.1. Sources button or indicator appears on a completed response

**File:** `tests/source-attribution/sources-visible.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, send a message, and wait for the response to complete
    - expect: A 'Sources' button or text indicator is visible in the message actions area below the response

#### 8.2. Clicking Sources button shows source document details

**File:** `tests/source-attribution/sources-dialog-opens.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, send a message, wait for the response, and click the Sources button
    - expect: A dialog or expandable panel opens showing source document information
    - expect: The source title 'Source Document' (from mock server) is visible
    - expect: Page number or document reference information is shown

#### 8.3. Copy button copies the response text to clipboard

**File:** `tests/source-attribution/copy-button.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, send a message, and wait for the response to complete
    - expect: A copy button is visible in the message actions area
  2. Click the copy button
    - expect: A visual confirmation (e.g., the icon changes or a toast notification appears) indicates the text was copied to the clipboard

### 9. Message Feedback (Like/Dislike)

**Seed:** `seed.spec.ts`

#### 9.1. Like and dislike buttons appear on a completed assistant message

**File:** `tests/feedback/like-dislike-buttons-visible.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, send a message, and wait for the response to complete
    - expect: A thumbs-up (like) button is visible in the message actions area
    - expect: A thumbs-down (dislike) button is visible in the message actions area

#### 9.2. Clicking the like button marks the message as liked

**File:** `tests/feedback/like-button-click.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, send a message, wait for the response to complete
    - expect: Like and dislike buttons are visible
  2. Click the thumbs-up (like) button
    - expect: The like button shows a visual active/filled state indicating the message has been liked

#### 9.3. Clicking the dislike button opens a feedback input

**File:** `tests/feedback/dislike-button-opens-feedback.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, send a message, wait for the response, and click the dislike button
    - expect: A feedback form or popover appears requesting the reason for disliking
    - expect: Options or a text input for specifying the feedback detail are visible

### 10. Pro/Con Perspective

**Seed:** `seed.spec.ts`

#### 10.1. Evaluate position (pro/con) button appears on assistant messages

**File:** `tests/pro-con/pro-con-button-visible.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality and a specific party, send a message, and wait for the response to complete
    - expect: An 'Evaluate position' button with a pro/con icon is visible in the message actions area

#### 10.2. Clicking 'Evaluate position' triggers a pro/con streaming response

**File:** `tests/pro-con/pro-con-generates-perspective.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality and a party, send a message, wait for response, and click 'Evaluate position'
    - expect: The pro/con button disappears or shows a loading state
    - expect: A pro/con perspective is streamed into an expandable section below the message
    - expect: The expandable section shows pros and cons with clear labels

### 11. Persisted Chat Sessions

**Seed:** `seed.spec.ts`

#### 11.1. URL includes chat_id after the first message is sent

**File:** `tests/persisted-sessions/url-includes-chat-id.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, and send a message
    - expect: The URL updates to include chat_id= as a query parameter
    - expect: The chat_id value is a non-empty string

#### 11.2. Page title updates to reflect the conversation topic after the response completes

**File:** `tests/persisted-sessions/page-title-updates.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, send a message, and wait for the response to complete
    - expect: The browser tab title changes from 'chatvote' to include the conversation title returned by the mock server (e.g., 'Test Chat Title')

#### 11.3. Navigating directly to a chat session URL loads the conversation

**File:** `tests/persisted-sessions/direct-session-url.spec.ts`

**Steps:**
  1. Start a chat session, note the chat_id in the URL, then navigate to /chat/<chatId> directly in a new tab or after reload
    - expect: The conversation history for that session loads and is displayed
    - expect: The page shows previous user messages and assistant responses

#### 11.4. Sidebar shows chat history entries for authenticated users

**File:** `tests/persisted-sessions/sidebar-chat-history.spec.ts`

**Steps:**
  1. Log in with a test user account, start a chat session and send a message, then check the sidebar
    - expect: The sidebar displays a history section with an entry for the current conversation
    - expect: The entry shows the conversation title or a preview of the first question

### 12. Authentication

**Seed:** `seed.spec.ts`

#### 12.1. Log in button is visible in the sidebar

**File:** `tests/authentication/login-button-visible.spec.ts`

**Steps:**
  1. Navigate to /chat on desktop viewport
    - expect: A button with text matching 'Log in' or 'Se connecter' is visible in the sidebar

#### 12.2. Clicking the Log in button opens the authentication dialog

**File:** `tests/authentication/login-button-opens-dialog.spec.ts`

**Steps:**
  1. Navigate to /chat and click the 'Log in' button in the sidebar
    - expect: A modal dialog appears
    - expect: The dialog contains an email input field and a password input field
    - expect: A 'Log in' submit button is visible
    - expect: OAuth buttons for Google and Microsoft are visible

#### 12.3. Login form validates required fields

**File:** `tests/authentication/login-form-validation.spec.ts`

**Steps:**
  1. Navigate to /chat and open the login dialog
    - expect: The login form is visible
  2. Click the submit button without filling in email or password
    - expect: HTML5 validation or custom validation prevents form submission
    - expect: Error messages or required field indicators are shown for the email and password fields

#### 12.4. Login form validates email format

**File:** `tests/authentication/login-form-email-validation.spec.ts`

**Steps:**
  1. Navigate to /chat and open the login dialog
    - expect: The login form is visible
  2. Enter 'notanemail' in the email field and a valid password, then click submit
    - expect: The form does not submit
    - expect: An email format validation error is shown

#### 12.5. Login with invalid credentials shows an error toast

**File:** `tests/authentication/login-invalid-credentials.spec.ts`

**Steps:**
  1. Navigate to /chat and open the login dialog
    - expect: The login form is visible
  2. Enter a valid email format and an incorrect password, then click submit
    - expect: A toast notification appears with a message matching 'The entered credentials are invalid' or similar
    - expect: The user remains on the login form

#### 12.6. Switching from login to registration mode

**File:** `tests/authentication/login-to-register-switch.spec.ts`

**Steps:**
  1. Navigate to /chat and open the login dialog
    - expect: The form shows 'Log in' mode with a 'Don't have an account yet?' link
  2. Click the 'Sign up' link or button
    - expect: The form switches to registration mode
    - expect: The heading changes to 'Sign up'
    - expect: The description changes to the registration description

#### 12.7. Forgot password link shows the password reset form

**File:** `tests/authentication/forgot-password-form.spec.ts`

**Steps:**
  1. Navigate to /chat, open the login dialog
    - expect: The login form is visible
  2. Click the 'Forgot password?' button
    - expect: The form switches to the password reset view
    - expect: An email field and a 'Send link' button are shown
    - expect: A description about receiving a reset link is visible

#### 12.8. Successful login updates the UI to show user avatar

**File:** `tests/authentication/successful-login-ui-update.spec.ts`

**Steps:**
  1. Navigate to /chat and open the login dialog
    - expect: The login form is visible
  2. Enter valid credentials for a seeded test user account and click submit
    - expect: A success toast notification appears matching 'Successfully logged in'
    - expect: The login button in the sidebar is replaced by a user avatar or account button
    - expect: The dialog closes automatically

#### 12.9. Anonymous users can still use the chat without logging in

**File:** `tests/authentication/anonymous-user-can-chat.spec.ts`

**Steps:**
  1. Navigate to /chat without logging in and select a municipality
    - expect: The chat input becomes enabled
    - expect: The user can type and send a message without being prompted to log in
  2. Send a message
    - expect: The message is sent and a streaming response is received
    - expect: No authentication error or forced login prompt appears

### 13. Theme and Language (i18n)

**Seed:** `seed.spec.ts`

#### 13.1. Theme toggle switches between light and dark mode

**File:** `tests/theme-language/theme-toggle.spec.ts`

**Steps:**
  1. Navigate to /chat and note the current value of the data-theme attribute on the html element
    - expect: The initial theme is applied (either 'light' or 'dark')
  2. Click the theme toggle button (matching 'Toggle theme' or 'Changer de theme')
    - expect: The data-theme attribute on the html element changes to the opposite theme
    - expect: The visual appearance of the page reflects the new theme (background colour changes)
  3. Click the theme toggle button again
    - expect: The theme reverts to the original value

#### 13.2. Language switcher combobox is visible

**File:** `tests/theme-language/language-switcher-visible.spec.ts`

**Steps:**
  1. Navigate to /chat
    - expect: A combobox or select element for language switching is visible in the header

#### 13.3. Switching language from French to English translates the UI

**File:** `tests/theme-language/switch-to-english.spec.ts`

**Steps:**
  1. Navigate to /chat (likely loads in French by default)
    - expect: French UI text is present (e.g., sidebar shows 'Se connecter', municipality placeholder shows 'commune')
  2. Open the language switcher and select English (EN)
    - expect: The UI text switches to English
    - expect: The login button text changes to 'Log in'
    - expect: The municipality input placeholder changes to use 'municipality'
    - expect: The disclaimer text changes to the English version

#### 13.4. Switching language from English to French translates the UI

**File:** `tests/theme-language/switch-to-french.spec.ts`

**Steps:**
  1. Navigate to /chat and switch to English first
    - expect: UI is in English
  2. Open the language switcher and select French (FR)
    - expect: The UI text switches to French
    - expect: The login button text changes to 'Se connecter'
    - expect: The municipality placeholder shows 'commune'

#### 13.5. Theme preference persists across page navigation

**File:** `tests/theme-language/theme-persists.spec.ts`

**Steps:**
  1. Navigate to /chat and toggle the theme to dark mode
    - expect: Dark mode is active
  2. Navigate to /guide and then back to /chat
    - expect: Dark mode is still active — the data-theme attribute retains the dark value

#### 13.6. Language preference persists across page navigation

**File:** `tests/theme-language/language-persists.spec.ts`

**Steps:**
  1. Navigate to /chat and switch the language to English
    - expect: UI is in English
  2. Navigate to /guide then back to /chat
    - expect: The UI remains in English after navigation

### 14. Responsive Layout

**Seed:** `seed.spec.ts`

#### 14.1. Sidebar is hidden by default on mobile viewport

**File:** `tests/responsive/mobile-sidebar-hidden.spec.ts`

**Steps:**
  1. Set the browser viewport to 390x844 (iPhone 14 Pro) and navigate to /chat
    - expect: The sidebar navigation links (Legal notice, Privacy, etc.) are not visible
    - expect: The sidebar is in a collapsed/hidden state by default

#### 14.2. Sidebar toggle button is visible on mobile

**File:** `tests/responsive/mobile-sidebar-toggle-visible.spec.ts`

**Steps:**
  1. Set the browser viewport to 390x844 and navigate to /chat
    - expect: A sidebar toggle/hamburger button is visible in the header area

#### 14.3. Opening the sidebar on mobile shows navigation links

**File:** `tests/responsive/mobile-sidebar-open.spec.ts`

**Steps:**
  1. Set the browser viewport to 390x844 and navigate to /chat
    - expect: The sidebar is hidden
  2. Click the sidebar toggle button
    - expect: The sidebar opens as an overlay
    - expect: Navigation links including Legal notice, Privacy, and Guide are now visible

#### 14.4. Sidebar is visible by default on desktop viewport

**File:** `tests/responsive/desktop-sidebar-visible.spec.ts`

**Steps:**
  1. Set the browser viewport to 1280x800 and navigate to /chat
    - expect: The sidebar is visible without needing to toggle it
    - expect: Navigation links are immediately visible

#### 14.5. Chat layout is usable on tablet viewport

**File:** `tests/responsive/tablet-layout.spec.ts`

**Steps:**
  1. Set the browser viewport to 768x1024 (iPad) and navigate to /chat
    - expect: The page renders without horizontal overflow or broken layout
    - expect: The municipality input is visible and usable
    - expect: The header elements are accessible

#### 14.6. Chat input and message area are scrollable on small screens

**File:** `tests/responsive/small-screen-scroll.spec.ts`

**Steps:**
  1. Set viewport to 375x667 (iPhone SE), navigate to /chat, select a municipality, and send several messages
    - expect: The messages area scrolls vertically
    - expect: The chat input remains fixed or accessible at the bottom
    - expect: No content is cut off or inaccessible

### 15. Guide and Help Dialog

**Seed:** `seed.spec.ts`

#### 15.1. Help icon button in the header opens the HowTo guide dialog

**File:** `tests/guide/help-icon-opens-dialog.spec.ts`

**Steps:**
  1. Navigate to /chat
    - expect: The help icon (HelpCircleIcon) button is visible in the header
  2. Click the help icon button
    - expect: A guide dialog/modal opens
    - expect: The dialog explains how ChatVote works

#### 15.2. Guide dialog can be closed

**File:** `tests/guide/guide-dialog-close.spec.ts`

**Steps:**
  1. Navigate to /chat and open the guide dialog by clicking the help icon
    - expect: The guide dialog is open
  2. Click the close button within the dialog or press Escape
    - expect: The dialog closes and the chat page is visible again

#### 15.3. Guide page /guide has substantive content

**File:** `tests/guide/guide-page-content.spec.ts`

**Steps:**
  1. Navigate directly to http://localhost:3000/guide
    - expect: The guide page renders without errors
    - expect: A title or heading for the guide is visible
    - expect: Explanatory content about how ChatVote works is present on the page

### 16. Error States and Edge Cases

**Seed:** `seed.spec.ts`

#### 16.1. Rate limit state disables chat input and shows a message

**File:** `tests/error-states/rate-limit-disabled-input.spec.ts`

**Steps:**
  1. Set the system_status Firestore document field is_at_rate_limit to true and navigate to /chat
    - expect: The chat input is disabled
    - expect: A message is shown indicating the server is overloaded (matching 'Server currently overloaded' or 'Serveur surchargé')

#### 16.2. Server overloaded state shows a suggestion to log in

**File:** `tests/error-states/rate-limit-login-prompt.spec.ts`

**Steps:**
  1. Set the is_at_rate_limit flag to true and navigate to /chat as an anonymous user
    - expect: The overloaded message includes a prompt or link to 'log in' so the user can ask their own questions

#### 16.3. Chat session error page renders for /chat/[chatId]/error

**File:** `tests/error-states/chat-session-error-page.spec.ts`

**Steps:**
  1. Navigate to a chat session URL that will trigger a server error during data loading
    - expect: An error boundary component is rendered
    - expect: An error message or retry option is shown to the user

#### 16.4. Very long message input is handled gracefully

**File:** `tests/error-states/long-message-input.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, and type a message exceeding 1000 characters into the chat input
    - expect: The input accepts the text without crashing
    - expect: The send button is enabled
    - expect: Submitting the long message sends it without errors

#### 16.5. Special characters in message input are handled correctly

**File:** `tests/error-states/special-characters-input.spec.ts`

**Steps:**
  1. Navigate to /chat, select a municipality, and type a message containing special characters: '<script>alert(1)</script>' and emojis
    - expect: The input accepts and displays the text safely (no XSS execution)
    - expect: Submitting the message sends it as plain text
    - expect: The response area renders the reply without script injection
