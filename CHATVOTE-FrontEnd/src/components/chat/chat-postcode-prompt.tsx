"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { MunicipalitySearch } from "@components/election-flow";
import { type Municipality } from "@lib/election/election.types";

const ChatPostcodePrompt = () => {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [selectedMunicipality, setSelectedMunicipality] =
    useState<Municipality | null>(null);

  const municipalityCode = useMemo(() => {
    return searchParams.get("municipality_code") || undefined;
  }, [searchParams]);

  const handleSelectMunicipality = useCallback(
    (municipality: Municipality) => {
      setSelectedMunicipality(municipality);

      // If already set to this value, don't touch the router.
      const currentCode = searchParams.get("municipality_code");
      if (currentCode === municipality.code) {
        return;
      }

      const next = new URLSearchParams(searchParams.toString());
      next.set("municipality_code", municipality.code);

      // Keep user on the same page, just update querystring.
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  // Watch URL changes: if municipality_code disappears but we still have a selected
  // municipality, restore the query param.
  useEffect(() => {
    if (!selectedMunicipality) return;

    const currentCode = searchParams.get("municipality_code");
    if (currentCode) return;

    const next = new URLSearchParams(searchParams.toString());
    next.set("municipality_code", selectedMunicipality.code);

    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }, [pathname, router, searchParams, selectedMunicipality]);

  return (
    <div className="flex flex-col items-center gap-6">
      <MunicipalitySearch
        selectedMunicipality={selectedMunicipality}
        onSelectMunicipality={handleSelectMunicipality}
        municipalityCode={municipalityCode}
      />
    </div>
  );
};

export default ChatPostcodePrompt;
