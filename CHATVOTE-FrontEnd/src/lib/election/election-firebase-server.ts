"use server";

import { unstable_cache as cache } from "next/cache";

import { CacheTags } from "@lib/cache-tags";
import { db } from "@lib/firebase/firebase-admin";
import { getPartiesById } from "@lib/firebase/firebase-server";
import { type PartyDetails } from "@lib/party-details";

import { type Candidate, type Municipality } from "./election.types";

// =============================================================================
// MUNICIPALITIES
// =============================================================================

// In-memory cache for municipalities (avoids 2MB Next.js cache limit)
let municipalitiesCache: Municipality[] | null = null;
let municipalitiesCacheTimestamp: number = 0;
const CACHE_TTL = 24 * 60 * 60 * 1000; // 24 hours

// Load all municipalities into memory
async function loadMunicipalities(): Promise<Municipality[]> {
  const now = Date.now();

  // Return cached data if still valid
  if (
    municipalitiesCache !== null &&
    now - municipalitiesCacheTimestamp < CACHE_TTL
  ) {
    return municipalitiesCache;
  }

  try {
    const snapshot = await db.collection("municipalities").get();

    const municipalities = snapshot.docs.map(
      (docSnap) => docSnap.data() as Municipality,
    );

    // Sort by population once (descending)
    municipalities.sort((a, b) => (b.population || 0) - (a.population || 0));

    // Update cache
    municipalitiesCache = municipalities;
    municipalitiesCacheTimestamp = now;

    return municipalities;
  } catch (error) {
    console.error("Error loading municipalities:", error);
    return municipalitiesCache ?? [];
  }
}

// Get all municipalities (for client-side prefetch and local search)
export async function getAllMunicipalities(): Promise<Municipality[]> {
  return loadMunicipalities();
}

// Search municipalities - substring search, case insensitive
export async function searchMunicipalities(
  searchTerm: string,
): Promise<Municipality[]> {
  if (!searchTerm || searchTerm.length < 2) {
    return [];
  }

  const municipalities = await loadMunicipalities();
  const searchLower = searchTerm.trim().toLowerCase();
  const isNumericSearch = /^\d+$/.test(searchLower);

  const results = municipalities.filter((municipality) => {
    if (isNumericSearch) {
      // Search by postal code or INSEE code
      if (municipality.code.includes(searchLower)) {
        return true;
      }
      return municipality.codesPostaux.some((cp) => cp.includes(searchLower));
    }

    // Search by name (substring, case insensitive)
    return municipality.nom.toLowerCase().includes(searchLower);
  });

  // Already sorted by population from loadMunicipalities
  return results;
}

// Get municipality by INSEE code
export async function getMunicipalityByCode(
  code: string,
): Promise<Municipality | null> {
  try {
    const docSnap = await db.collection("municipalities").doc(code).get();

    if (!docSnap.exists) {
      return null;
    }

    return docSnap.data() as Municipality;
  } catch (error) {
    console.error("Error fetching municipality:", error);
    return null;
  }
}

// =============================================================================
// CANDIDATES
// =============================================================================

async function getCandidatesImpl(): Promise<Candidate[]> {
  try {
    const snapshot = await db.collection("candidates").get();

    const candidates = snapshot.docs.map(
      (docSnap) => docSnap.data() as Candidate,
    );

    return candidates;
  } catch (error) {
    console.error("Error fetching candidates:", error);
    return [];
  }
}

export const getCandidates = cache(getCandidatesImpl, undefined, {
  revalidate: 60 * 60,
  tags: [CacheTags.CANDIDATES],
});

// Get candidates for a specific municipality
export async function getCandidatesByMunicipality(
  municipalityCode: string,
): Promise<Candidate[]> {
  // Bypass cache for now
  const candidates = await getCandidatesImpl();

  const filteredCandidates = candidates.filter(
    (candidate) => candidate.municipality_code === municipalityCode,
  );

  // Sort by presence_score (descending)
  filteredCandidates.sort((a, b) => b.presence_score - a.presence_score);

  return filteredCandidates;
}

// Get parties present in a specific municipality (via candidates)
export async function getPartiesByMunicipality(
  municipalityCode: string,
): Promise<PartyDetails[]> {
  const candidates = await getCandidatesByMunicipality(municipalityCode);

  // Extract unique party IDs from all candidates
  const partyIds = [...new Set(candidates.flatMap((c) => c.party_ids))];

  if (partyIds.length === 0) {
    return [];
  }

  // Fetch party details
  const parties = await getPartiesById(partyIds);

  return parties;
}
