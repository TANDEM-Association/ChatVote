import {
  type GroupedMessage,
  type MessageFeedback,
  type MessageItem,
  type VotingBehavior,
} from "@lib/stores/chat-store.types";
import { type User } from "@lib/types/auth";
import { firestoreTimestampToDate, generateUuid } from "@lib/utils";
import { initializeApp } from "firebase/app";
import { connectAuthEmulator, getAuth } from "firebase/auth";
import {
  arrayUnion,
  collection,
  connectFirestoreEmulator,
  doc,
  getDoc,
  getDocs,
  getFirestore,
  limit,
  onSnapshot,
  orderBy,
  query,
  setDoc,
  Timestamp,
  updateDoc,
  where,
} from "firebase/firestore";

import { type ChatSession, type LlmSystemStatus } from "./firebase.types";
import { firebaseConfig } from "./firebase-config";

const app = initializeApp(firebaseConfig);

export const auth = getAuth(app);
const db = getFirestore(app);

if (process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true") {
  connectFirestoreEmulator(db, "localhost", 8081);
  connectAuthEmulator(auth, "http://localhost:9099", { disableWarnings: true });
}

export async function createChatSession(
  userId: string,
  partyIds: string[],
  sessionId: string,
  tenantId?: string,
): Promise<void> {
  return await setDoc(doc(db, "chat_sessions", sessionId), {
    user_id: userId,
    party_ids: partyIds,
    created_at: Timestamp.now(),
    updated_at: Timestamp.now(),
    ...(tenantId ? { tenant_id: tenantId } : {}),
  });
}

export async function getUsersChatHistory(uid: string): Promise<ChatSession[]> {
  const history = await getDocs(
    query(
      collection(db, "chat_sessions"),
      where("user_id", "==", uid),
      orderBy("updated_at", "desc"),
      orderBy("created_at", "desc"),
      limit(30),
    ),
  );

  return history.docs.map((doc) => ({
    id: doc.id,
    ...doc.data(),
  })) as ChatSession[];
}

export function listenToHistory(
  uid: string,
  callback: (history: ChatSession[]) => void,
) {
  const unsubscribe = onSnapshot(
    query(
      collection(db, "chat_sessions"),
      where("user_id", "==", uid),
      orderBy("updated_at", "desc"),
      orderBy("created_at", "desc"),
      limit(15),
    ),
    (snapshot) => {
      callback(
        snapshot.docs.map((doc) => ({
          id: doc.id,
          ...doc.data(),
        })) as ChatSession[],
      );
    },
  );

  return unsubscribe;
}

export function listenToSystemStatus(
  callback: (status: LlmSystemStatus) => void,
) {
  const unsubscribe = onSnapshot(
    doc(db, "system_status", "llm_status"),
    (snapshot) => {
      callback({
        is_at_rate_limit: snapshot.data()?.is_at_rate_limit ?? false,
      });
    },
  );

  return unsubscribe;
}

export async function getChatSession(sessionId: string) {
  const session = await getDoc(doc(db, "chat_sessions", sessionId));
  return {
    id: session.id,
    ...session.data(),
  } as ChatSession;
}

export async function getChatSessionMessages(sessionId: string) {
  const messagesRef = query(
    collection(db, "chat_sessions", sessionId, "messages"),
    orderBy("created_at", "asc"),
  );

  const snapshot = await getDocs(messagesRef);
  return snapshot.docs.map((doc) => {
    const data = doc.data();
    return {
      ...data,
      id: doc.id,
      messages: data.messages.map((message: MessageItem) => ({
        ...message,
        created_at: firestoreTimestampToDate(message.created_at),
      })),
    } as GroupedMessage;
  });
}

export async function updateChatSession(
  sessionId: string,
  data: Partial<ChatSession>,
) {
  await updateDoc(doc(db, "chat_sessions", sessionId), data);
}

export async function addMessageToGroupedMessageOfChatSession(
  sessionId: string,
  groupedMessageId: string,
  message: MessageItem,
) {
  await setDoc(
    doc(db, "chat_sessions", sessionId, "messages", groupedMessageId),
    {
      id: groupedMessageId,
      messages: arrayUnion(message),
      created_at: Timestamp.now(),
    },
    { merge: true },
  );
}

async function getGroupedMessage(sessionId: string, groupedMessageId: string) {
  const groupedMessage = await getDoc(
    doc(db, "chat_sessions", sessionId, "messages", groupedMessageId),
  );
  if (!groupedMessage.exists()) {
    return { id: groupedMessageId, messages: [] } as unknown as GroupedMessage;
  }
  return {
    id: groupedMessage.id,
    ...groupedMessage.data(),
  } as GroupedMessage;
}

export async function addProConPerspectiveToMessage(
  sessionId: string,
  groupedMessageId: string,
  messageId: string,
  proConPerspective: MessageItem,
) {
  const groupedMessage = await getGroupedMessage(sessionId, groupedMessageId);

  if (!groupedMessage.messages?.length) return;

  const groupedMessageRef = doc(
    db,
    "chat_sessions",
    sessionId,
    "messages",
    groupedMessageId,
  );

  await updateDoc(groupedMessageRef, {
    messages: groupedMessage.messages.map((message: MessageItem) => {
      if (message.id === messageId) {
        return {
          ...message,
          pro_con_perspective: proConPerspective,
        };
      }

      return message;
    }),
  });
}

export async function addVotingBehaviorToMessage(
  sessionId: string,
  groupedMessageId: string,
  messageId: string,
  votingBehavior: VotingBehavior,
) {
  const groupedMessage = await getGroupedMessage(sessionId, groupedMessageId);

  if (!groupedMessage.messages?.length) return;

  const groupedMessageRef = doc(
    db,
    "chat_sessions",
    sessionId,
    "messages",
    groupedMessageId,
  );

  await updateDoc(groupedMessageRef, {
    messages: groupedMessage.messages.map((message: MessageItem) => {
      if (message.id === messageId) {
        return {
          ...message,
          voting_behavior: votingBehavior,
        };
      }

      return message;
    }),
  });
}

export async function addUserMessageToChatSession(
  sessionId: string,
  message: string,
) {
  const messageId = generateUuid();

  await setDoc(doc(db, "chat_sessions", sessionId, "messages", messageId), {
    id: messageId,
    messages: [
      {
        id: generateUuid(),
        content: message,
        sources: [],
        created_at: Timestamp.now(),
        role: "user",
      },
    ],
    quick_replies: [],
    role: "user",
    created_at: Timestamp.now(),
  } satisfies GroupedMessage);
}

export async function updateQuickRepliesOfMessage(
  sessionId: string,
  messageId: string,
  quickReplies: string[],
) {
  await updateDoc(doc(db, "chat_sessions", sessionId, "messages", messageId), {
    quick_replies: quickReplies,
  });
}

export async function updateTitleOfMessage(sessionId: string, title: string) {
  await updateDoc(doc(db, "chat_sessions", sessionId), {
    title,
  });
}

export async function updateMessageInChatSession(
  sessionId: string,
  messageId: string,
  data: Partial<GroupedMessage>,
) {
  await updateDoc(
    doc(db, "chat_sessions", sessionId, "messages", messageId),
    data,
  );
}

export async function updateMessageFeedback(
  sessionId: string,
  groupedMessageId: string,
  messageId: string,
  feedback: MessageFeedback,
) {
  const groupedMessage = await getGroupedMessage(sessionId, groupedMessageId);

  const groupedMessageRef = doc(
    db,
    "chat_sessions",
    sessionId,
    "messages",
    groupedMessageId,
  );

  await updateDoc(groupedMessageRef, {
    messages: groupedMessage.messages.map((message: MessageItem) => {
      if (message.id === messageId) {
        return {
          ...message,
          feedback,
        };
      }

      return message;
    }),
  });
}

export async function getUser(uid: string): Promise<Partial<User>> {
  const user = await getDoc(doc(db, "users", uid));
  const data = user.data();

  const surveyTimestamp = data?.survey_status?.timestamp
    ? firestoreTimestampToDate(data.survey_status.timestamp)
    : undefined;

  return {
    survey_status:
      data?.survey_status && surveyTimestamp
        ? {
            state: data.survey_status.state,
            timestamp: surveyTimestamp,
          }
        : undefined,
    newsletter_allowed: data?.newsletter_allowed,
    clicked_away_login_reminder: data?.clicked_away_login_reminder
      ? firestoreTimestampToDate(data.clicked_away_login_reminder)
      : undefined,
    keep_up_to_date_email: data?.keep_up_to_date_email,
  };
}

export async function updateUserData(uid: string, data: Partial<User>) {
  await setDoc(doc(db, "users", uid), data, { merge: true });
}

export async function userAllowNewsletter(uid: string, allowed: boolean) {
  await setDoc(
    doc(db, "users", uid),
    {
      newsletter_allowed: allowed,
    },
    { merge: true },
  );
}
