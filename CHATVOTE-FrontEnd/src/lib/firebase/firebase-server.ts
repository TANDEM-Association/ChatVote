"use server";

import { unstable_cache as cache } from "next/cache";
import { headers } from "next/headers";

import { CacheTags } from "@lib/cache-tags";
import { ASSISTANT_ID, GROUP_PARTY_ID } from "@lib/constants";
import { type PartyDetails } from "@lib/party-details";
import {
  type GroupedMessage,
  type MessageItem,
} from "@lib/stores/chat-store.types";
import { type Auth, type User } from "@lib/types/auth";
import { firestoreTimestampToDate } from "@lib/utils";
import { initializeServerApp } from "firebase/app";
import { getAuth as getFirebaseAuth } from "firebase/auth";

import {
  type ChatSession,
  type LlmSystemStatus,
  type ProposedQuestion,
} from "./firebase.types";
import { db } from "./firebase-admin";
import { firebaseConfig } from "./firebase-config";

/** Strip non-serializable Firestore objects (Timestamps, GeoPoints, etc.)
 *  so data can safely cross the Server → Client Component boundary. */
function serialize<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

// --- Firebase Auth (still uses Client SDK for authStateReady) ---

async function getServerApp({
  useHeaders = true,
}: { useHeaders?: boolean } = {}) {
  let authIdToken: string | undefined;

  if (useHeaders) {
    const headersList = await headers();
    authIdToken = headersList.get("authorization")?.split(" ")[1];
  }

  return initializeServerApp(firebaseConfig, { authIdToken });
}

async function getFirebaseAuthUser() {
  if (process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true") {
    return null;
  }

  const serverApp = await getServerApp();
  const firebaseAuth = getFirebaseAuth(serverApp);
  await firebaseAuth.authStateReady();

  if (!firebaseAuth.currentUser) {
    return null;
  }

  return firebaseAuth.currentUser;
}

export async function getAuth(): Promise<Auth> {
  try {
    const firebaseUser = await getFirebaseAuthUser();

    if (!firebaseUser) {
      return { session: null, user: null };
    }

    const userDoc = await db.collection("users").doc(firebaseUser.uid).get();
    const userData = userDoc.data() as Partial<User> | undefined;

    const surveyTimestamp = userData?.survey_status?.timestamp
      ? firestoreTimestampToDate(userData.survey_status.timestamp)
      : undefined;

    return {
      session: {
        uid: firebaseUser.uid,
        isAnonymous: firebaseUser.isAnonymous,
        emailVerified: firebaseUser.emailVerified,
      },
      user: {
        uid: firebaseUser.uid,
        email: firebaseUser.email,
        displayName: firebaseUser.displayName,
        photoURL: firebaseUser.photoURL,
        phoneNumber: firebaseUser.phoneNumber,
        providerId: firebaseUser.providerId,
        providerData: firebaseUser.providerData,
        metadata: {
          creationTime: firebaseUser.metadata.creationTime,
          lastSignInTime: firebaseUser.metadata.lastSignInTime,
        },
        // Business data
        survey_status:
          userData?.survey_status && surveyTimestamp
            ? {
                state: userData.survey_status.state,
                timestamp: surveyTimestamp,
              }
            : undefined,
        newsletter_allowed: userData?.newsletter_allowed,
        clicked_away_login_reminder: userData?.clicked_away_login_reminder
          ? firestoreTimestampToDate(userData.clicked_away_login_reminder)
          : undefined,
        keep_up_to_date_email: userData?.keep_up_to_date_email,
      },
    };
  } catch {
    return { session: null, user: null };
  }
}

// --- Firestore reads (Admin SDK — emulator-safe) ---

async function getPartiesImpl() {
  try {
    const snapshot = await db
      .collection("parties")
      .orderBy("election_result_forecast_percent", "desc")
      .get();

    return snapshot.docs.map((doc) => serialize(doc.data())) as PartyDetails[];
  } catch {
    return [];
  }
}

export const getParties =
  process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true"
    ? getPartiesImpl
    : cache(getPartiesImpl, undefined, {
        revalidate: false,
        tags: [CacheTags.PARTIES],
      });

async function getPartyImpl(partyId: string) {
  const docSnap = await db.collection("parties").doc(partyId).get();

  if (!docSnap.exists) {
    return;
  }

  return serialize(docSnap.data()) as PartyDetails;
}

export const getParty = cache(getPartyImpl, undefined, {
  revalidate: false,
  tags: [CacheTags.PARTIES],
});

export async function getPartiesByIdImpl(partyIds: string[]) {
  const parties = await Promise.all(partyIds.map(getParty));

  return parties.filter(Boolean) as PartyDetails[];
}

export const getPartiesById = cache(getPartiesByIdImpl, undefined, {
  revalidate: false,
  tags: [CacheTags.PARTIES],
});

export async function getChatSession(sessionId: string) {
  const docSnap = await db.collection("chat_sessions").doc(sessionId).get();

  if (!docSnap.exists) {
    return;
  }

  const data = docSnap.data();

  if (!data) {
    return;
  }

  return {
    id: docSnap.id,
    user_id: data.user_id,
    party_id: data.party_id,
    is_public: data.is_public,
    title: data.title,
    party_ids: data.party_ids,
    tenant_id: data.tenant_id,
    municipality_code: data.municipality_code,
    scope: data.scope,
    updated_at: firestoreTimestampToDate(data.updated_at),
    created_at: firestoreTimestampToDate(data.created_at),
  } as ChatSession;
}

export async function getUsersChatSessions(
  uid: string,
): Promise<ChatSession[]> {
  try {
    const snapshot = await db
      .collection("chat_sessions")
      .where("user_id", "==", uid)
      .orderBy("updated_at", "desc")
      .orderBy("created_at", "desc")
      .limit(15)
      .get();

    return snapshot.docs.map((doc) => {
      const data = doc.data();
      return serialize({
        id: doc.id,
        ...data,
        updated_at: firestoreTimestampToDate(data.updated_at),
        created_at: firestoreTimestampToDate(data.created_at),
      }) as ChatSession;
    });
  } catch {
    return [];
  }
}

export async function getChatSessionMessages(sessionId: string) {
  const snapshot = await db
    .collection("chat_sessions")
    .doc(sessionId)
    .collection("messages")
    .orderBy("created_at", "asc")
    .get();

  return snapshot.docs.map((doc) => {
    const data = doc.data();
    return serialize({
      ...data,
      id: doc.id,
      created_at: firestoreTimestampToDate(data.created_at),
      messages: data.messages.map((message: MessageItem) => ({
        ...message,
        created_at: firestoreTimestampToDate(message.created_at),
      })),
    }) as GroupedMessage;
  });
}

async function getProposedQuestionsImpl(partyIds?: string[]) {
  const normalizedId = partyIds?.length
    ? partyIds.length > 1
      ? GROUP_PARTY_ID
      : partyIds[0]
    : ASSISTANT_ID;

  const snapshot = await db
    .collection("proposed_questions")
    .doc(normalizedId)
    .collection("questions")
    .where("location", "==", "chat")
    .get();

  const questions = snapshot.docs.map((doc) => {
    return serialize({
      id: doc.id,
      partyId: normalizedId,
      ...doc.data(),
    }) as ProposedQuestion;
  });

  return questions.sort(() => Math.random() - 0.5);
}

export const getProposedQuestions = cache(getProposedQuestionsImpl, undefined, {
  revalidate: 60 * 60 * 24,
  tags: [CacheTags.PROPOSED_QUESTIONS],
});

async function getHomeInputProposedQuestionsImpl() {
  const snapshot = await db
    .collection("proposed_questions")
    .doc(ASSISTANT_ID)
    .collection("questions")
    .where("location", "==", "home")
    .get();

  return snapshot.docs.map((doc) => {
    return serialize({
      id: doc.id,
      partyId: ASSISTANT_ID,
      ...doc.data(),
    }) as ProposedQuestion;
  });
}

export const getHomeInputProposedQuestions = cache(
  getHomeInputProposedQuestionsImpl,
  undefined,
  {
    revalidate: 60 * 60 * 24,
    tags: [CacheTags.HOME_PROPOSED_QUESTIONS],
  },
);

export async function getSystemStatus() {
  const docSnap = await db.collection("system_status").doc("llm_status").get();

  return {
    is_at_rate_limit: docSnap.data()?.is_at_rate_limit ?? false,
  } as LlmSystemStatus;
}
