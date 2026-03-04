import { type UserInfo, type UserMetadata } from "firebase/auth";

/**
 * Session - Authentication state
 */
export type Session = {
  uid: string;
  isAnonymous: boolean;
  emailVerified: boolean;
};

/**
 * User - All user information (profile + business data)
 */
export type User = {
  uid: string;
  email: string | null;
  displayName: string | null;
  photoURL: string | null;
  phoneNumber: string | null;
  providerId: string;
  providerData: UserInfo[];
  metadata: UserMetadata;
  // Business data
  survey_status?: {
    state: "opened" | "closed";
    timestamp: Date;
  } | null;
  newsletter_allowed?: boolean;
  clicked_away_login_reminder?: Date;
  keep_up_to_date_email?: string;
};

/**
 * Auth - Union type ensuring session and user are both present or both null
 */
export type Auth =
  | {
      session: Session;
      user: User;
    }
  | {
      session: null;
      user: null;
    };
