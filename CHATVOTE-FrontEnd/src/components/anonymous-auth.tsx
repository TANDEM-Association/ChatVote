"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import {
  auth,
  getUser,
  updateUserData as updateUserDataFirebase,
} from "@lib/firebase/firebase";
import { type Auth, type User } from "@lib/types/auth";
import { signInAnonymously } from "firebase/auth";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

type AuthContextType = {
  session: Auth["session"];
  user: Auth["user"];
  loading: boolean;
  updateUser: (data: Partial<User>) => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType>({
  session: null,
  user: null,
  loading: true,
  updateUser: async () => {},
  refreshUser: async () => {},
});

export const useAuth = () => {
  return useContext(AuthContext);
};

type AuthProviderProps = {
  children: React.ReactNode;
  initialAuth: Auth;
};

export const AuthProvider = ({ children, initialAuth }: AuthProviderProps) => {
  const t = useTranslations("common");
  const [session, setSession] = useState<Auth["session"]>(initialAuth.session);
  const [user, setUser] = useState<Auth["user"]>(initialAuth.user);
  const [loading, setLoading] = useState(true);

  const createSession = useCallback(async () => {
    try {
      await signInAnonymously(auth);
    } catch (error) {
      console.error(error);
      toast.error(t("errorReload"));
    }
  }, [t]);

  const fetchUser = async (uid: string) => {
    const user = await getUser(uid);

    setUser((currentUser) => {
      if (!currentUser) {
        return null;
      }

      return {
        ...currentUser,
        ...user,
      };
    });

    setLoading(false);
  };

  useEffect(() => {
    const unsubscribe = auth.onAuthStateChanged(async (firebaseUser) => {
      if (firebaseUser !== null) {
        setSession({
          uid: firebaseUser.uid,
          isAnonymous: firebaseUser.isAnonymous,
          emailVerified: firebaseUser.emailVerified,
        });

        setUser((currentUser) => ({
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
          // Preserve existing business data
          survey_status: currentUser?.survey_status,
          newsletter_allowed: currentUser?.newsletter_allowed,
          clicked_away_login_reminder: currentUser?.clicked_away_login_reminder,
          keep_up_to_date_email: currentUser?.keep_up_to_date_email,
        }));

        await fetchUser(firebaseUser.uid);
      } else {
        await createSession();
      }
    });

    return unsubscribe;
  }, [createSession]);

  async function updateUser(data: Partial<User>) {
    if (!session?.uid) {
      return;
    }

    await updateUserDataFirebase(session.uid, data);
    await fetchUser(session.uid);
  }

  async function refreshUser() {
    setLoading(true);

    const firebaseUser = auth.currentUser;

    if (firebaseUser) {
      setSession({
        uid: firebaseUser.uid,
        isAnonymous: firebaseUser.isAnonymous,
        emailVerified: firebaseUser.emailVerified,
      });

      setUser((currentUser) => ({
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
        survey_status: currentUser?.survey_status,
        newsletter_allowed: currentUser?.newsletter_allowed,
        clicked_away_login_reminder: currentUser?.clicked_away_login_reminder,
        keep_up_to_date_email: currentUser?.keep_up_to_date_email,
      }));

      await fetchUser(firebaseUser.uid);
    }
  }

  return (
    <AuthContext.Provider
      value={{ session, user, updateUser, loading, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
};

// Backwards compatibility alias
export const useAnonymousAuth = useAuth;

// Re-export types for convenience
export type { Auth, User } from "@lib/types/auth";
