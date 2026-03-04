import { type Party } from "./generated";

/** Extends backend Party model with frontend-only Firestore fields. */
export type PartyDetails = Party & {
  /** From Firestore only — not part of backend API response. */
  election_result_forecast_percent: number;
};
