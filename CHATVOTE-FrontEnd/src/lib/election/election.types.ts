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
};

export type MunicipalitiesDocument = {
  [code: string]: Municipality;
};

// Helper to check if a candidate is in a coalition
export function isCoalitionCandidate(candidate: Candidate): boolean {
  return candidate.party_ids.length >= 2;
}
