// Types for election-related data

import { type Candidate as GeneratedCandidate } from "../generated";

// Candidate types
// Extends backend Candidate model. Overrides nullable fields that are guaranteed
// non-null when read from Firestore, and drops backend-only election_type_id.

export type Candidate = Omit<
  GeneratedCandidate,
  "election_type_id" | "position" | "bio" | "created_at" | "updated_at"
> & {
  position: string;
  bio: string;
  created_at: string;
  updated_at: string;
  is_second_round?: boolean;
};

export type CandidatesMetadata = {
  description: string;
  last_updated: string;
  notes: {
    presence_score: string;
    party_ids: string;
    municipality_code: string;
  };
};

export type CandidatesDocument = {
  _metadata: CandidatesMetadata;
  [key: string]: Candidate | CandidatesMetadata;
};

// Municipality types

export type MunicipalityEpci = {
  code: string;
  nom: string;
};

export type MunicipalityDepartement = {
  code: string;
  nom: string;
};

export type MunicipalityRegion = {
  code: string;
  nom: string;
};

export type Municipality = {
  code: string; // Code INSEE
  nom: string;
  zone: "metro" | "dom" | "tom";
  population: number;
  surface: number;
  codesPostaux: string[];
  codeRegion: string;
  codeDepartement: string;
  siren: string;
  codeEpci: string;
  epci: MunicipalityEpci;
  departement: MunicipalityDepartement;
  region: MunicipalityRegion;
  _syncedAt: string;
  has_electoral_data?: boolean;
};

export type MunicipalitiesDocument = {
  [code: string]: Municipality;
};

// Electoral list types (from official candidatures CSV)

export type ElectoralList = {
  panel_number: number;
  list_label: string;
  list_short_label: string;
  nuance_code: string | null;
  nuance_label: string | null;
  head_first_name: string;
  head_last_name: string;
};

export type ElectoralListsByCommune = {
  commune_code: string;
  commune_name: string;
  list_count: number;
  lists: ElectoralList[];
  lists_round_2?: ElectoralList[];
  list_count_round_2?: number;
};

// Helper to check if a candidate is in a coalition
export function isCoalitionCandidate(candidate: Candidate): boolean {
  return candidate.party_ids.length >= 2;
}
