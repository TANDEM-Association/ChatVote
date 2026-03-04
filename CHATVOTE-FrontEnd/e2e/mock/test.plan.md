# ChatVote E2E Test Plan

## Application Overview

ChatVote is an AI-powered political information chatbot for French elections. Users can ask questions to multiple political parties simultaneously and receive source-backed, streamed answers via Socket.IO. The application is a Next.js 16 app using Firebase Auth (anonymous, Google, email, Microsoft), Firestore for session persistence, Zustand for state management, and Socket.IO for real-time streaming. The test environment uses a mock Socket.IO server on port 8080 that returns deterministic responses, Firebase Auth and Firestore emulators, and the Next.js dev server on port 3000. Key routes are: / (redirects to /chat), /chat (new chat with optional party_id and q query params), /chat/[chatId] (persisted chat session), /guide, /legal-notice, /privacy-policy, /donate.

## Test Scenarios

### 1. Landing Page and Navigation

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 1.1. Root URL redirects to /chat

**File:** `CHATVOTE-FrontEnd/e2e/mock/landing-and-navigation.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/
    - expect: The browser is redirected to http://localhost:3000/chat without manual intervention
    - expect: The chat page is displayed with the ChatVote logo and input area

#### 1.2. /chat page displays the empty chat view with logo and input

**File:** `CHATVOTE-FrontEnd/e2e/mock/landing-and-navigation.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat
    - expect: The page loads successfully with HTTP 200
    - expect: The ChatVote logo (chatvote.svg) is visible in the empty view
    - expect: A text input field with a placeholder is visible
    - expect: A submit button (ArrowUp icon) is visible but disabled because the input is empty
    - expect: The page header is visible with theme toggle, language switcher, help button, and new chat button

#### 1.3. Header elements are present and functional

**File:** `CHATVOTE-FrontEnd/e2e/mock/landing-and-navigation.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat
    - expect: The header is visible at the top of the page
  2. Identify the theme mode toggle button in the header
    - expect: A theme toggle button is present in the header
  3. Identify the language switcher in the header
    - expect: A language switcher control is present in the header
  4. Identify the help/guide button (question mark icon) in the header
    - expect: A help icon button is visible in the top-right area
  5. Identify the new chat dropdown button in the header
    - expect: A new chat button is visible in the top-right area

#### 1.4. Guide page loads at /guide

**File:** `CHATVOTE-FrontEnd/e2e/mock/landing-and-navigation.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/guide
    - expect: The page loads successfully
    - expect: The guide/how-it-works content is displayed

#### 1.5. Legal notice page loads at /legal-notice

**File:** `CHATVOTE-FrontEnd/e2e/mock/landing-and-navigation.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/legal-notice
    - expect: The page loads successfully with legal notice content visible

#### 1.6. Privacy policy page loads at /privacy-policy

**File:** `CHATVOTE-FrontEnd/e2e/mock/landing-and-navigation.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/privacy-policy
    - expect: The page loads successfully with privacy policy content visible

#### 1.7. Donate page loads at /donate

**File:** `CHATVOTE-FrontEnd/e2e/mock/landing-and-navigation.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/donate
    - expect: The donate page loads successfully

### 2. Chat Input and Message Submission

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 2.1. Submit button is disabled when input is empty

**File:** `CHATVOTE-FrontEnd/e2e/mock/chat-input.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for the page to be idle
    - expect: The page is loaded and anonymous authentication has completed
  2. Locate the chat input field and verify it is empty
    - expect: The input field is empty
  3. Locate the submit button (ArrowUp icon)
    - expect: The submit button has the disabled attribute set

#### 2.2. Submit button becomes enabled when text is typed in the input

**File:** `CHATVOTE-FrontEnd/e2e/mock/chat-input.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for the page to be idle
    - expect: The chat page loads and anonymous auth completes
  2. Click on the chat input field and type 'What is your policy on education?'
    - expect: The typed text appears in the input field
  3. Observe the submit button state
    - expect: The submit button is now enabled (not disabled)

#### 2.3. Pressing Enter submits the message

**File:** `CHATVOTE-FrontEnd/e2e/mock/chat-input.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for anonymous auth
    - expect: The chat page is loaded
  2. Click the chat input and type 'What is your policy on education?'
    - expect: Text appears in the input field
  3. Press the Enter key
    - expect: The message is submitted
    - expect: The user message 'What is your policy on education?' appears in the chat
    - expect: The input field is cleared

#### 2.4. Clicking the submit button sends the message

**File:** `CHATVOTE-FrontEnd/e2e/mock/chat-input.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for anonymous auth
    - expect: The chat page is loaded
  2. Type 'Tell me about healthcare policies' in the chat input
    - expect: Text is visible in the input field
  3. Click the submit button (ArrowUp icon)
    - expect: The message is submitted and appears in the conversation
    - expect: The input is cleared after submission

#### 2.5. Whitespace-only input does not submit

**File:** `CHATVOTE-FrontEnd/e2e/mock/chat-input.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for anonymous auth
    - expect: The chat page is loaded
  2. Type only spaces into the chat input
    - expect: The submit button remains disabled or submission is prevented
  3. Attempt to press Enter
    - expect: No message is sent; the conversation remains empty

#### 2.6. Input is disabled while a response is being streamed

**File:** `CHATVOTE-FrontEnd/e2e/mock/chat-input.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for anonymous auth
    - expect: The chat page is loaded
  2. Type 'What are your economic policies?' and submit
    - expect: The message is sent and the mock server starts responding
  3. Immediately observe the input field during the streaming period
    - expect: The input field is disabled during streaming
    - expect: The submit button is disabled during streaming
    - expect: A loading border trail animation appears on the input

### 3. Streamed Party Responses

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 3.1. Sending a message triggers party response cards

**File:** `CHATVOTE-FrontEnd/e2e/mock/streamed-responses.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for anonymous auth to complete
    - expect: The chat page is loaded
  2. Type 'What are your policies on climate change?' in the input and submit
    - expect: The user message appears in the conversation
  3. Wait for the mock server to respond (allow up to 2 seconds)
    - expect: Party response cards appear in the chat (one per responding party)
    - expect: Each card shows streaming text content: 'Response chunk 0. Response chunk 1. Response chunk 2.'
    - expect: The response cards display a party identifier or icon

#### 3.2. Streaming completes and full response is displayed

**File:** `CHATVOTE-FrontEnd/e2e/mock/streamed-responses.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, wait for auth, and submit 'What is your stance on immigration?'
    - expect: The user message appears
  2. Wait for streaming to complete (all party_response_complete events received)
    - expect: The complete response text is visible: 'This is a complete test response for the party.'
    - expect: The loading animation on the input disappears
    - expect: The input field becomes enabled again

#### 3.3. Multiple party responses appear in a carousel when multiple parties respond

**File:** `CHATVOTE-FrontEnd/e2e/mock/streamed-responses.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for auth
    - expect: The chat page loads
  2. Submit the message 'What are your housing policies?'
    - expect: The user message appears
  3. Wait for the mock server response to complete
    - expect: A carousel component is visible containing multiple party response cards (party-a and party-b)
    - expect: Previous and next navigation buttons are visible on the carousel
    - expect: A slide counter indicator shows the current party and total party count

#### 3.4. Carousel navigation between party responses works

**File:** `CHATVOTE-FrontEnd/e2e/mock/streamed-responses.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, wait for auth, and submit a question
    - expect: Party responses are displayed in a carousel
  2. Click the next arrow button on the carousel
    - expect: The carousel slides to the second party response
    - expect: The slide counter updates to reflect the new position (e.g., 2/2)
  3. Click the previous arrow button on the carousel
    - expect: The carousel returns to the first party response
    - expect: The slide counter shows position 1/2

#### 3.5. Chat session ID appears in the URL after the first message

**File:** `CHATVOTE-FrontEnd/e2e/mock/streamed-responses.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat
    - expect: The URL is /chat
  2. Submit any message
    - expect: The URL changes to /chat/[chatId] where [chatId] is a unique session identifier
    - expect: The chat session is persisted in the URL

### 4. Quick Reply Suggestions

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 4.1. Quick replies appear after a complete response

**File:** `CHATVOTE-FrontEnd/e2e/mock/quick-replies.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for auth
    - expect: The page loads
  2. Submit 'What are your policies on education?' and wait for the full response including quick replies
    - expect: After streaming completes, quick reply suggestion buttons appear above the input field
    - expect: The quick replies match the mock server response: 'What about education?', 'Tell me about healthcare', 'Economic policies'

#### 4.2. Clicking a quick reply sends it as a new message

**File:** `CHATVOTE-FrontEnd/e2e/mock/quick-replies.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, wait for auth, and submit an initial question. Then wait for quick replies to appear
    - expect: Quick reply buttons are visible above the input
  2. Click the quick reply button labeled 'What about education?'
    - expect: The text 'What about education?' is submitted as a new user message
    - expect: The message appears in the conversation
    - expect: A new round of streaming begins from the mock server

#### 4.3. Quick replies are disabled while a response is loading

**File:** `CHATVOTE-FrontEnd/e2e/mock/quick-replies.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, submit a question, and wait for quick replies to appear
    - expect: Quick replies are visible
  2. Click a quick reply to trigger a new message. Immediately observe the quick reply buttons during the loading state
    - expect: The quick reply buttons are disabled (have the disabled attribute) during the loading/streaming period

#### 4.4. Quick replies scroll horizontally when they overflow

**File:** `CHATVOTE-FrontEnd/e2e/mock/quick-replies.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, submit a question, and wait for quick replies to appear
    - expect: Quick reply buttons are rendered
  2. Inspect the quick replies container for overflow behavior
    - expect: The quick replies container allows horizontal scrolling when the combined width of buttons exceeds the container width
    - expect: No vertical scrollbar is visible in the quick replies area

### 5. Source Attribution

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 5.1. Sources button appears on a completed party response

**File:** `CHATVOTE-FrontEnd/e2e/mock/source-attribution.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, wait for auth, submit a question, and wait for streaming to complete
    - expect: Party response cards are visible with complete text
  2. Look for a Sources button (book icon) on the party response card
    - expect: A 'Sources' button with a book/bookmark icon is visible on the response card

#### 5.2. Clicking the Sources button opens a modal with source documents

**File:** `CHATVOTE-FrontEnd/e2e/mock/source-attribution.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, submit a question, wait for the full response, and locate the Sources button
    - expect: The Sources button is visible
  2. Click the Sources button
    - expect: A modal dialog opens
    - expect: The modal has a title 'Sources' (or the French equivalent)
    - expect: A description text is shown below the title
    - expect: Source items are listed, including 'Source Document' from the mock server
    - expect: Each source item shows a numbered badge, content preview, and page number

#### 5.3. Sources modal can be closed

**File:** `CHATVOTE-FrontEnd/e2e/mock/source-attribution.spec.ts`

**Steps:**
  1. Open the Sources modal by clicking the Sources button on a completed response
    - expect: The Sources modal is open
  2. Click the modal close button or press Escape
    - expect: The Sources modal closes and the main chat view is restored

### 6. Pro/Con Perspective

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 6.1. Pro/Con button is available on a completed party response

**File:** `CHATVOTE-FrontEnd/e2e/mock/pro-con-perspective.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, wait for auth, submit 'What is your position on nuclear energy?', and wait for the full response
    - expect: A party response card is visible with complete text
  2. Look for the Pro/Con button on the response card action bar
    - expect: A Pro/Con perspective button (with an icon indicating pros and cons) is visible in the message action area

#### 6.2. Clicking Pro/Con shows a loading state then the perspective

**File:** `CHATVOTE-FrontEnd/e2e/mock/pro-con-perspective.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, submit a question, wait for the full response, then click the Pro/Con button on the response card
    - expect: A loading spinner with animated text sequence appears (e.g., 'Understanding topic...', 'Analyzing feasibility...')
  2. Wait for the mock server to return the pro_con_perspective_complete event
    - expect: The loading state disappears
    - expect: The pro/con content appears: 'Pro: Good policy. Con: High cost.'
    - expect: The pro/con section is automatically expanded (visible)

#### 6.3. Pro/Con section can be collapsed and expanded

**File:** `CHATVOTE-FrontEnd/e2e/mock/pro-con-perspective.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, submit a question, wait for full response, click Pro/Con, and wait for the perspective to load
    - expect: The pro/con section is expanded and visible
  2. Click the collapse/eye button on the pro/con section
    - expect: The pro/con section collapses and the content is hidden
    - expect: A hint text appears: 'Contains an evaluated position'
  3. Click the expand/eye button again
    - expect: The pro/con section expands and the content is visible again

### 7. Voting Behavior

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 7.1. Voting behavior button is available on a completed party response

**File:** `CHATVOTE-FrontEnd/e2e/mock/voting-behavior.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, wait for auth, submit a question, and wait for the full response
    - expect: A party response card is visible
  2. Look for the voting behavior button on the response card action area
    - expect: A voting behavior summary button is visible on the completed response card

#### 7.2. Clicking voting behavior shows loading then result

**File:** `CHATVOTE-FrontEnd/e2e/mock/voting-behavior.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, submit a question, wait for the full response, then click the voting behavior button
    - expect: A loading spinner with animated messages appears (e.g., 'Searching motions...', 'Analyzing submitters...')
  2. Wait for the mock server voting_behavior_complete event
    - expect: The loading state disappears
    - expect: The voting behavior summary section appears with the text 'No voting records found for this topic.'
    - expect: The section is expanded by default

#### 7.3. Voting behavior section can be collapsed and expanded

**File:** `CHATVOTE-FrontEnd/e2e/mock/voting-behavior.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, submit a question, wait for full response, click the voting behavior button, and wait for results
    - expect: The voting behavior section is visible and expanded
  2. Click the collapse button (eye icon) on the voting behavior section
    - expect: The section collapses
    - expect: A hint text shows 'Contains voting behavior of the party'
  3. Click the expand button to re-open it
    - expect: The voting behavior summary is visible again

### 8. Sidebar Navigation

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 8.1. Desktop sidebar is visible and contains navigation links

**File:** `CHATVOTE-FrontEnd/e2e/mock/sidebar.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat in a desktop-width browser (1280x720) and wait for the page to load
    - expect: The sidebar is visible on the left side of the screen
  2. Inspect the sidebar contents
    - expect: The ChatVote logo and Tandem logo are visible
    - expect: A 'New Chat' section is present with new chat buttons
    - expect: A 'Support ChatVote' section shows Login, Donate, and Feedback buttons
    - expect: An 'Information' section shows About, How it works, Legal notice, and Privacy links

#### 8.2. Mobile sidebar is hidden by default and can be toggled

**File:** `CHATVOTE-FrontEnd/e2e/mock/sidebar.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat at mobile viewport (390x844) and wait for the page to load
    - expect: The sidebar is not visible by default on mobile
  2. Click the sidebar trigger button (hamburger/menu icon) in the top-left header area
    - expect: The sidebar slides in from the left and is visible
    - expect: The sidebar shows the ChatVote logo and navigation sections
  3. Click the sidebar trigger or close button again
    - expect: The sidebar closes and is hidden

#### 8.3. Chat history appears in sidebar after a conversation

**File:** `CHATVOTE-FrontEnd/e2e/mock/sidebar.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, wait for auth, and submit a question. Wait for the full response
    - expect: A chat session is created with the title 'Test Chat Title' (from mock server's quick_replies_and_title_ready event)
  2. Look at the sidebar history section
    - expect: The chat history section appears with the current session title 'Test Chat Title'
    - expect: The current session is visually highlighted in the history list

#### 8.4. Clicking a history item navigates to that chat session

**File:** `CHATVOTE-FrontEnd/e2e/mock/sidebar.spec.ts`

**Steps:**
  1. Start by having at least one completed chat session visible in the sidebar history
    - expect: A history item with a title is visible in the sidebar
  2. Navigate to http://localhost:3000/chat to start a fresh chat
    - expect: The new empty chat page loads
  3. Click the history item in the sidebar
    - expect: The browser navigates to /chat/[chatId] for the selected session
    - expect: The previous conversation is shown in the chat area

#### 8.5. New chat button in sidebar opens party selection

**File:** `CHATVOTE-FrontEnd/e2e/mock/sidebar.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for page load
    - expect: The page loads
  2. Locate and click the new chat or party selection area in the sidebar
    - expect: New chat options are shown including a ChatVote multi-party option and individual party cards

### 9. New Chat Creation and Party Selection

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 9.1. New chat dropdown in header shows party cards

**File:** `CHATVOTE-FrontEnd/e2e/mock/new-chat-party-selection.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for the page to load
    - expect: The chat page loads with the header visible
  2. Click the new chat dropdown button in the top-right header
    - expect: A dropdown panel opens with a 'New Chat' title and subtitle
    - expect: Party card options are displayed in a grid (3 columns)
    - expect: A ChatVote multi-party option is visible among the cards

#### 9.2. Selecting a party from the new chat dropdown navigates to a party-specific chat

**File:** `CHATVOTE-FrontEnd/e2e/mock/new-chat-party-selection.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat. Open the new chat dropdown by clicking the new chat button in the header
    - expect: The dropdown is open with party cards
  2. Click on any party card from the dropdown
    - expect: The dropdown closes
    - expect: The browser navigates to /chat?party_id=[selected-party-id]
    - expect: The empty chat view shows the selected party's logo

#### 9.3. URL parameter party_id pre-selects the party on the chat page

**File:** `CHATVOTE-FrontEnd/e2e/mock/new-chat-party-selection.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat?party_id=party-a
    - expect: The empty chat view shows the party logo for 'party-a'
    - expect: The party is pre-selected for the chat session

#### 9.4. URL parameter q pre-populates and submits an initial question

**File:** `CHATVOTE-FrontEnd/e2e/mock/new-chat-party-selection.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat?q=What+is+your+climate+policy
    - expect: The question 'What is your climate policy' is automatically submitted
    - expect: The user message appears in the conversation
    - expect: The mock server responds with party response cards

#### 9.5. URL parameter chat_id redirects to the specific chat session

**File:** `CHATVOTE-FrontEnd/e2e/mock/new-chat-party-selection.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat?chat_id=some-chat-id
    - expect: The browser is redirected to /chat/some-chat-id

### 10. Authentication

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 10.1. Anonymous authentication is created automatically on page load

**File:** `CHATVOTE-FrontEnd/e2e/mock/authentication.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for the page to reach network idle
    - expect: The page loads without any login prompt being forced on the user
    - expect: The anonymous user is silently authenticated in the background (Firebase emulator creates an anonymous user)
    - expect: The chat input is functional without requiring explicit login

#### 10.2. Login button opens a login/register form in a modal or sidebar

**File:** `CHATVOTE-FrontEnd/e2e/mock/authentication.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for the page to load
    - expect: The page loads
  2. Click the Login button in the sidebar (the user icon button)
    - expect: A login/register form appears as a modal
    - expect: The form has an email input field
    - expect: The form has a password input field
    - expect: A 'Forgot password?' link is visible
    - expect: A Login or Register submit button is present
    - expect: Google and Microsoft OAuth buttons are visible

#### 10.3. Login form validates required fields

**File:** `CHATVOTE-FrontEnd/e2e/mock/authentication.spec.ts`

**Steps:**
  1. Open the login modal by clicking the Login button in the sidebar
    - expect: The login form is displayed
  2. Click the Login submit button without entering any credentials
    - expect: The browser's native validation prevents submission
    - expect: The email field is highlighted as required

#### 10.4. Toggle between login and register views

**File:** `CHATVOTE-FrontEnd/e2e/mock/authentication.spec.ts`

**Steps:**
  1. Open the login modal
    - expect: The login view is shown with 'Login' as the form title
  2. Click the 'Register' link/button to switch to registration
    - expect: The form switches to registration mode with 'Register' as the title and description
  3. Click the 'Login' link/button to switch back
    - expect: The form returns to login mode

#### 10.5. Forgot password link shows the password reset form

**File:** `CHATVOTE-FrontEnd/e2e/mock/authentication.spec.ts`

**Steps:**
  1. Open the login modal
    - expect: The login form is displayed
  2. Click the 'Forgot password?' button
    - expect: The form transitions to a password reset view where the user can enter their email to receive a reset link

#### 10.6. Login with invalid credentials shows an error toast

**File:** `CHATVOTE-FrontEnd/e2e/mock/authentication.spec.ts`

**Steps:**
  1. Open the login modal, enter an email 'wrong@example.com' and password 'wrongpassword', then click Login
    - expect: An error toast notification appears with text indicating invalid credentials (auth/invalid-credential error message)

### 11. Theme and Language

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 11.1. Theme toggle switches between light and dark mode

**File:** `CHATVOTE-FrontEnd/e2e/mock/theme-and-language.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for the page to load
    - expect: The page loads in the default theme
  2. Click the theme mode toggle button in the header
    - expect: The application theme switches (e.g., from light to dark or vice versa)
    - expect: The background color and text colors change accordingly
  3. Click the theme toggle button again
    - expect: The theme switches back to the previous mode

#### 11.2. Language switcher changes the UI language between French and English

**File:** `CHATVOTE-FrontEnd/e2e/mock/theme-and-language.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for the page to load
    - expect: The page loads in the default language (French)
  2. Click the language switcher in the header
    - expect: Language options are presented (FR and EN)
  3. Select the English language option
    - expect: The UI text updates to English
    - expect: Placeholder text in the chat input, button labels, and section headings are now in English
  4. Switch back to French
    - expect: The UI text returns to French

### 12. How To Guide Dialog

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 12.1. Help button opens the how-to guide dialog

**File:** `CHATVOTE-FrontEnd/e2e/mock/guide-dialog.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for the page to load
    - expect: The page is loaded with the header visible
  2. Click the help/question mark icon button in the top-right header
    - expect: A dialog or modal opens containing a guide explaining how to use ChatVote
    - expect: The guide content describes how to interact with parties, how to ask questions, etc.
  3. Close the dialog by pressing Escape or clicking the close button
    - expect: The dialog closes and the chat page is displayed normally

### 13. Responsive Layout

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 13.1. Chat page layout is usable on mobile viewport (390x844)

**File:** `CHATVOTE-FrontEnd/e2e/mock/responsive-layout.spec.ts`

**Steps:**
  1. Set the browser viewport to 390x844 (iPhone 14) and navigate to http://localhost:3000/chat
    - expect: The page loads without horizontal overflow or broken layout
    - expect: The chat input is visible at the bottom of the screen
    - expect: The header is visible at the top with the mobile sidebar trigger button
  2. Submit a message and wait for the response
    - expect: Party response cards are displayed and readable on mobile
    - expect: The carousel navigation is functional on mobile

#### 13.2. Chat page layout is correct on tablet viewport (768x1024)

**File:** `CHATVOTE-FrontEnd/e2e/mock/responsive-layout.spec.ts`

**Steps:**
  1. Set the browser viewport to 768x1024 and navigate to http://localhost:3000/chat
    - expect: The layout displays correctly at tablet width
    - expect: The sidebar may be shown or hidden depending on the breakpoint
    - expect: The chat input and header are correctly positioned

#### 13.3. Desktop layout shows the sidebar permanently

**File:** `CHATVOTE-FrontEnd/e2e/mock/responsive-layout.spec.ts`

**Steps:**
  1. Set the browser viewport to 1280x800 and navigate to http://localhost:3000/chat
    - expect: The sidebar is visible on the left without needing to toggle it
    - expect: The main chat area occupies the remaining space to the right of the sidebar
    - expect: No mobile sidebar trigger is shown in the header (md:hidden class applies)

### 14. Error States and Edge Cases

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 14.1. Socket disconnected banner appears when WebSocket connection is lost

**File:** `CHATVOTE-FrontEnd/e2e/mock/error-states.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and wait for the socket to connect
    - expect: The page loads normally with no disconnection banner
  2. Simulate a WebSocket disconnection (e.g., stop the mock server or use network interception to block the socket connection)
    - expect: A disconnection banner or notification appears in the chat header area indicating the socket is disconnected

#### 14.2. Chat error page is shown for an invalid chat ID

**File:** `CHATVOTE-FrontEnd/e2e/mock/error-states.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat/nonexistent-invalid-chat-id-12345
    - expect: The page either shows a 404/not found state or the error.tsx boundary is rendered
    - expect: The error page provides a way to return to the main chat page

#### 14.3. Scroll down indicator appears when chat content overflows

**File:** `CHATVOTE-FrontEnd/e2e/mock/error-states.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat and submit multiple questions to fill the chat area beyond the viewport height
    - expect: A scroll-down indicator button appears when the user is not at the bottom of the chat
  2. Click the scroll-down indicator
    - expect: The chat scrolls to the bottom and the indicator disappears

#### 14.4. Copy button on message copies content to clipboard

**File:** `CHATVOTE-FrontEnd/e2e/mock/error-states.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, submit a question, and wait for the full response
    - expect: A party response card is visible
  2. Find the copy button on the response card action bar and click it
    - expect: The message content is copied to the clipboard
    - expect: A visual feedback (icon change or toast) confirms the copy action

#### 14.5. Like/dislike feedback buttons are available on responses

**File:** `CHATVOTE-FrontEnd/e2e/mock/error-states.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, submit a question, and wait for a complete party response
    - expect: The party response card is visible
  2. Locate the like and dislike buttons on the response card
    - expect: Like (thumbs up) and dislike (thumbs down) buttons are visible in the message action area
  3. Click the like button
    - expect: The like button state changes to indicate it has been selected (e.g., filled icon or different color)

### 15. Persisted Chat Session Navigation

**Seed:** `CHATVOTE-FrontEnd/seed.spec.ts`

#### 15.1. Navigating to /chat/[chatId] restores a previous conversation

**File:** `CHATVOTE-FrontEnd/e2e/mock/persisted-sessions.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, wait for auth, submit a question, and wait for the full response. Note the chat ID from the URL
    - expect: The conversation is visible and the URL shows /chat/[chatId]
  2. Navigate away to http://localhost:3000/chat to start a new chat
    - expect: A fresh empty chat is shown
  3. Navigate back to /chat/[chatId] using the previously noted ID
    - expect: The previous conversation is restored from Firestore
    - expect: The user message and party responses are visible
    - expect: Quick replies from the previous session may be shown

#### 15.2. Page title updates to the chat session title after a response

**File:** `CHATVOTE-FrontEnd/e2e/mock/persisted-sessions.spec.ts`

**Steps:**
  1. Navigate to http://localhost:3000/chat, wait for auth, and submit a question. Wait for the quick_replies_and_title_ready event from the mock server
    - expect: The document or page title updates to reflect 'Test Chat Title' (from the mock server response)
