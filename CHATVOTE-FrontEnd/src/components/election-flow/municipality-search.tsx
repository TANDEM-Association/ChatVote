"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { type Municipality } from "@lib/election/election.types";
import { BarChart3, ChevronDownIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Button } from "../ui/button";
import { Input } from "../ui/input";

const RESULTS_PER_PAGE = 20;

// Client-side search helper (pure function)
function filterMunicipalities(
  municipalities: Municipality[],
  searchTerm: string,
): Municipality[] {
  if (!searchTerm || searchTerm.length < 2) {
    return [];
  }

  const searchLower = searchTerm.trim().toLowerCase();
  const isNumericSearch = /^\d+$/.test(searchLower);

  return municipalities.filter((municipality) => {
    if (isNumericSearch) {
      // Search by postal code or INSEE code
      if (municipality.code.includes(searchLower)) {
        return true;
      }
      return (municipality.codesPostaux ?? []).some((cp) => cp.includes(searchLower));
    }

    // Search by name (substring, case insensitive)
    return municipality.nom.toLowerCase().includes(searchLower);
  });
}

// Global client-side cache for municipalities (persists across component remounts)
let municipalitiesClientCache: Municipality[] | null = null;

// Fetch municipalities from API (with abort support)
async function fetchMunicipalities(
  signal?: AbortSignal,
): Promise<Municipality[]> {
  // Return cached data if available
  if (municipalitiesClientCache !== null) {
    return municipalitiesClientCache;
  }

  const response = await fetch("/api/municipalities", {
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch municipalities");
  }

  const data = (await response.json()) as Municipality[];
  municipalitiesClientCache = data;

  return data;
}

type Props = {
  selectedMunicipality?: Municipality | null;
  municipalityCode?: string;
  onSelectMunicipality: (municipality: Municipality) => void;
};

const MunicipalitySearch = ({
  selectedMunicipality,
  onSelectMunicipality,
  municipalityCode,
}: Props) => {
  const t = useTranslations("electionFlow");
  const [searchTerm, setSearchTerm] = useState("");
  const [municipalities, setMunicipalities] = useState<Municipality[]>(
    () => municipalitiesClientCache ?? [],
  );
  const [visibleCount, setVisibleCount] = useState(RESULTS_PER_PAGE);
  const [isLoadingData, setIsLoadingData] = useState(
    municipalitiesClientCache === null,
  );
  const [showSuggestions, setShowSuggestions] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);

  // Prefetch municipalities on mount (with AbortController for cleanup)
  useEffect(() => {
    // Skip if already cached (state is already initialized from cache)
    if (municipalitiesClientCache !== null) {
      handleSelectMunicipalityFromCodeProp(municipalitiesClientCache);
      return;
    }

    const abortController = new AbortController();

    fetchMunicipalities(abortController.signal)
      .then((data) => {
        if (!abortController.signal.aborted) {
          setMunicipalities(data);
          setIsLoadingData(false);
          handleSelectMunicipalityFromCodeProp(data);
        }
      })
      .catch((error) => {
        // Ignore abort errors
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }
        console.error("Failed to fetch municipalities:", error);
        if (!abortController.signal.aborted) {
          setIsLoadingData(false);
        }
      });

    return () => {
      abortController.abort();
    };
  }, []);

  // Filter municipalities locally (instant results)
  const allSuggestions = useMemo(() => {
    return filterMunicipalities(municipalities, searchTerm);
  }, [municipalities, searchTerm]);

  // Visible suggestions (paginated)
  const visibleSuggestions = allSuggestions.slice(0, visibleCount);
  const hasMore = allSuggestions.length > visibleCount;

  // Handle search input change (no debounce needed, filtering is instant)
  const handleSearchChange = useCallback((value: string) => {
    setSearchTerm(value);
    setVisibleCount(RESULTS_PER_PAGE);

    if (value.length < 2) {
      setShowSuggestions(false);
      return;
    }

    setShowSuggestions(true);
  }, []);

  // Load more results
  const handleShowMore = useCallback(() => {
    setVisibleCount((prev) => prev + RESULTS_PER_PAGE);
  }, []);

  // Handle municipality selection
  const handleSelectMunicipality = useCallback(
    (municipality: Municipality) => {
      setSearchTerm(municipality.nom);
      setShowSuggestions(false);
      onSelectMunicipality(municipality);
    },
    [onSelectMunicipality],
  );

  const handleSelectMunicipalityFromCodeProp = (
    localMunicipalities: Municipality[],
  ) => {
    if (
      !municipalityCode ||
      localMunicipalities.length === 0 ||
      selectedMunicipality?.code === municipalityCode
    ) {
      return;
    }

    const match = localMunicipalities.find((m) => m.code === municipalityCode);
    if (match) {
      onSelectMunicipality(match);
    }
  };

  // Close suggestions when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        suggestionsRef.current !== null &&
        !suggestionsRef.current.contains(event.target as Node) &&
        inputRef.current !== null &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setShowSuggestions(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  return (
    <div className="relative w-full space-y-4">
      {/* Selected municipality info */}
      {selectedMunicipality !== null && selectedMunicipality !== undefined && selectedMunicipality.nom ? (
        <div className="mt-3 flex flex-col items-center gap-4 text-center">
          <div className="text-2xl font-medium">
            {selectedMunicipality.nom}, {selectedMunicipality.codesPostaux?.[0]}
          </div>
          <div className="text-muted-foreground text-base">
            {selectedMunicipality.departement?.nom} •{" "}
            {selectedMunicipality.region?.nom}
          </div>
          <Link
            href={`/commune/${selectedMunicipality.code}`}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1.5 text-sm text-primary transition hover:bg-primary/20"
          >
            <BarChart3 className="size-3.5" />
            Voir le tableau de bord
          </Link>
        </div>
      ) : (
        <>
          <div>
            {t("municipalityPrompt")}
          </div>
          <Input
            ref={inputRef}
            type="text"
            placeholder={t("municipalityPlaceholder")}
            value={searchTerm}
            onChange={(e) => handleSearchChange(e.target.value)}
            onFocus={() => {
              if (allSuggestions.length > 0) {
                setShowSuggestions(true);
              }
            }}
            className={"px-4 py-2"}
            disabled={
              selectedMunicipality !== null &&
              selectedMunicipality !== undefined
            }
          />
          {/* Suggestions dropdown */}
          {showSuggestions && visibleSuggestions.length > 0 ? (
            <div
              ref={suggestionsRef}
              className="absolute top-28 z-50 w-full overflow-hidden rounded-3xl border border-border-strong bg-surface-input p-2 shadow-lg md:top-24"
            >
              <ul className="max-h-80 space-y-1 overflow-auto">
                {visibleSuggestions.map((municipality) => (
                  <li
                    key={municipality.code}
                    className="hover:bg-primary cursor-pointer rounded-md p-1 transition-all duration-300 ease-in-out first:rounded-t-2xl last:rounded-b-2xl"
                  >
                    <button
                      className="flex w-full flex-col items-start gap-2 px-3 py-2 text-left text-sm"
                      onClick={() => handleSelectMunicipality(municipality)}
                    >
                      <div className="font-medium">{municipality.nom}</div>
                      <div className="text-muted-foreground text-xs">
                        {(municipality.codesPostaux ?? []).slice(0, 2).join(", ")}
                        {(municipality.codesPostaux ?? []).length > 2
                          ? ` +${(municipality.codesPostaux ?? []).length - 2}`
                          : ""}{" "}
                        • {municipality.departement?.nom}
                      </div>
                    </button>
                  </li>
                ))}

                {/* Show more button */}
                {hasMore ? (
                  <li className="border-border border-t p-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full"
                      onClick={handleShowMore}
                    >
                      <ChevronDownIcon className="mr-2 size-4" />
                      {t("showMore", {
                        remaining: allSuggestions.length - visibleCount,
                      })}
                    </Button>
                  </li>
                ) : null}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
};

export default MunicipalitySearch;
