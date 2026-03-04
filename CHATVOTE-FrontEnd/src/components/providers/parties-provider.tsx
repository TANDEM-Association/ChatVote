"use client";
import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { type PartyDetails } from "@lib/party-details";

type PartiesContextType = {
  parties: PartyDetails[];
  partyCount: number;
};

export const PartiesContext = createContext<PartiesContextType | null>(null);

export type Props = {
  children: React.ReactNode;
  parties: PartyDetails[];
};

export const useParties = (partyIds?: string[]) => {
  const context = useContext(PartiesContext);
  if (context === null) {
    throw new Error("useParties must be used within a PartiesProvider");
  }

  const parties = useMemo(() => {
    if (partyIds !== undefined) {
      return context.parties?.filter((party) =>
        partyIds.includes(party.party_id),
      );
    }
    return context.parties;
  }, [context.parties, partyIds]);

  return parties;
};

export const useParty = (partyId: string) => {
  const parties = useParties([partyId]);

  if (!parties) {
    return undefined;
  }

  return parties[0];
};

function shuffleArray<T>(array: T[]): T[] {
  const shuffled = [...array];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

export const PartiesProvider = ({ children, parties }: Props) => {
  // Start with server-provided order to avoid hydration mismatch
  const [randomizedParties, setRandomizedParties] =
    useState<PartyDetails[]>(parties);

  // Shuffle only after hydration on client side
  useEffect(() => {
    setRandomizedParties(shuffleArray(parties));
  }, [parties]);

  return (
    <PartiesContext.Provider
      value={{
        parties: randomizedParties,
        partyCount: parties.length,
      }}
    >
      {children}
    </PartiesContext.Provider>
  );
};
