"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  trackCommunePageView,
  trackMunicipalitySearched,
} from "@lib/firebase/analytics";
import { type Municipality } from "@lib/election/election.types";
import { Loader2Icon } from "lucide-react";
import { useTranslations } from "next-intl";

import MiniDashboardCard from "../chat/mini-dashboard-card";
import { Input } from "../ui/input";

const DEBOUNCE_MS = 300;
const MIN_CHARS = 2;

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
  const [suggestions, setSuggestions] = useState<Municipality[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Auto-select municipality from URL code param on mount
  useEffect(() => {
    if (!municipalityCode || selectedMunicipality?.code === municipalityCode) {
      return;
    }

    fetch(`/api/municipalities?code=${encodeURIComponent(municipalityCode)}`)
      .then((r) => r.json())
      .then((data: Municipality | null) => {
        if (data) onSelectMunicipality(data);
      })
      .catch(() => {});
  }, [municipalityCode, selectedMunicipality, onSelectMunicipality]);

  // Debounced search
  const handleSearchChange = useCallback((value: string) => {
    setSearchTerm(value);

    if (debounceTimer.current) clearTimeout(debounceTimer.current);

    if (value.length < MIN_CHARS) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    debounceTimer.current = setTimeout(async () => {
      // Abort previous in-flight request
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      setIsLoading(true);
      try {
        const res = await fetch(
          `/api/municipalities?q=${encodeURIComponent(value)}`,
          { signal: abortRef.current.signal },
        );
        if (!res.ok) throw new Error("fetch failed");
        const data = (await res.json()) as Municipality[];
        setSuggestions(data);
        setShowSuggestions(data.length > 0);
        trackMunicipalitySearched({
          search_term: value,
          result_count: data.length,
        });
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        console.error("Municipality search failed:", err);
      } finally {
        setIsLoading(false);
      }
    }, DEBOUNCE_MS);
  }, []);

  const handleSelectMunicipality = useCallback(
    (municipality: Municipality) => {
      setSearchTerm(municipality.nom);
      setShowSuggestions(false);
      setSuggestions([]);
      trackCommunePageView({
        commune_code: municipality.code,
        commune_name: municipality.nom,
      });
      onSelectMunicipality(municipality);
    },
    [onSelectMunicipality],
  );

  // Close suggestions on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        suggestionsRef.current &&
        !suggestionsRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      abortRef.current?.abort();
    };
  }, []);

  return (
    <div className="relative w-full space-y-4">
      {selectedMunicipality?.nom ? (
        <div className="mt-3 flex flex-col items-center gap-4 text-center">
          <div className="text-2xl font-medium">
            {selectedMunicipality.nom}, {selectedMunicipality.codesPostaux?.[0]}
          </div>
          <div className="text-muted-foreground text-base">
            {selectedMunicipality.departement?.nom} •{" "}
            {selectedMunicipality.region?.nom}
            {selectedMunicipality.population
              ? ` • ${selectedMunicipality.population.toLocaleString()} hab.`
              : ""}
          </div>
          <MiniDashboardCard
            communeCode={selectedMunicipality.code}
            communeName={selectedMunicipality.nom}
          />
        </div>
      ) : (
        <>
          <div>{t("municipalityPrompt")}</div>
          <div className="relative">
            <Input
              ref={inputRef}
              type="text"
              placeholder={t("municipalityPlaceholder")}
              value={searchTerm}
              onChange={(e) => handleSearchChange(e.target.value)}
              onFocus={() => {
                if (suggestions.length > 0) setShowSuggestions(true);
              }}
              className="px-4 py-2"
            />
            {isLoading && (
              <Loader2Icon className="text-muted-foreground absolute top-1/2 right-3 size-4 -translate-y-1/2 animate-spin" />
            )}
          </div>

          {showSuggestions && suggestions.length > 0 && (
            <div
              ref={suggestionsRef}
              className="border-border-strong bg-surface-input absolute top-28 z-50 w-full overflow-hidden rounded-3xl border p-2 shadow-lg md:top-24"
            >
              <ul className="max-h-80 space-y-1 overflow-auto">
                {suggestions.map((municipality) => (
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
                        {municipality.population
                          ? ` • ${municipality.population.toLocaleString()} hab.`
                          : ""}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default MunicipalitySearch;
