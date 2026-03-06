"use client";

import React, { useCallback, useEffect, useState } from "react";

import { Button } from "@components/ui/button";
import { Input } from "@components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@components/ui/select";
import { Separator } from "@components/ui/separator";
import { SearchIcon, Loader2Icon, FlaskConicalIcon } from "lucide-react";

import {
  FiabiliteBadge,
  ScoreBadge,
  SourceDocBadge,
  ThemeBadge,
} from "./metadata-badge";

type MetadataSchema = {
  themes: string[];
  fiabilite_levels: Record<string, string>;
  namespaces: string[];
  collections: string[];
};

type SearchResult = {
  score: number;
  content: string;
  metadata: Record<string, unknown>;
};

type SearchResponse = {
  query: string;
  collection: string;
  filters: { theme?: string; max_fiabilite?: number; party_id?: string };
  results_count: number;
  results: SearchResult[];
};

export default function ExperimentPlayground() {
  const [schema, setSchema] = useState<MetadataSchema | null>(null);
  const [query, setQuery] = useState("");
  const [collection, setCollection] = useState("parties");
  const [theme, setTheme] = useState<string>("_all");
  const [maxFiabilite, setMaxFiabilite] = useState("4");
  const [partyId, setPartyId] = useState<string>("_all");
  const [loading, setLoading] = useState(false);

  // Side-by-side: filtered results and unfiltered results
  const [filteredResults, setFilteredResults] = useState<SearchResponse | null>(null);
  const [unfilteredResults, setUnfilteredResults] = useState<SearchResponse | null>(null);

  useEffect(() => {
    fetch("/api/experiment/schema")
      .then((r) => r.json())
      .then(setSchema)
      .catch(console.error);
  }, []);

  const search = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const baseBody = { query, collection, limit: 10 };
      const filteredBody = {
        ...baseBody,
        theme: theme !== "_all" ? theme : undefined,
        max_fiabilite: Number(maxFiabilite),
        party_id: partyId !== "_all" ? partyId : undefined,
      };
      const unfilteredBody = { ...baseBody, max_fiabilite: 4 };

      const [filteredRes, unfilteredRes] = await Promise.all([
        fetch("/api/experiment/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(filteredBody),
        }).then((r) => r.json()),
        fetch("/api/experiment/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(unfilteredBody),
        }).then((r) => r.json()),
      ]);

      setFilteredResults(filteredRes);
      setUnfilteredResults(unfilteredRes);
    } catch (e) {
      console.error("Search failed:", e);
    } finally {
      setLoading(false);
    }
  }, [query, collection, theme, maxFiabilite, partyId]);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <FlaskConicalIcon className="text-muted-foreground size-6" />
        <div>
          <h1 className="text-2xl font-bold">Chunk Metadata Explorer</h1>
          <p className="text-muted-foreground text-sm">
            Search the vector store with metadata filters. Compare filtered vs unfiltered retrieval.
          </p>
        </div>
      </div>

      <Separator />

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <label className="text-muted-foreground mb-1 block text-xs font-medium">
            Search Query
          </label>
          <div className="flex gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. politique environnementale"
              onKeyDown={(e) => e.key === "Enter" && search()}
            />
            <Button onClick={search} disabled={loading || !query.trim()}>
              {loading ? (
                <Loader2Icon className="size-4 animate-spin" />
              ) : (
                <SearchIcon className="size-4" />
              )}
              Search
            </Button>
          </div>
        </div>

        <div className="w-36">
          <label className="text-muted-foreground mb-1 block text-xs font-medium">
            Collection
          </label>
          <Select value={collection} onValueChange={setCollection}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="parties">Parties</SelectItem>
              <SelectItem value="candidates">Candidates</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="w-40">
          <label className="text-muted-foreground mb-1 block text-xs font-medium">
            Theme
          </label>
          <Select value={theme} onValueChange={setTheme}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_all">All themes</SelectItem>
              {schema?.themes.map((t) => (
                <SelectItem key={t} value={t}>
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="w-40">
          <label className="text-muted-foreground mb-1 block text-xs font-medium">
            Max Fiabilite
          </label>
          <Select value={maxFiabilite} onValueChange={setMaxFiabilite}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">1 - Government only</SelectItem>
              <SelectItem value="2">2 - + Official</SelectItem>
              <SelectItem value="3">3 - + Press</SelectItem>
              <SelectItem value="4">4 - All (no filter)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="w-44">
          <label className="text-muted-foreground mb-1 block text-xs font-medium">
            Namespace (Party/Candidate)
          </label>
          <Select value={partyId} onValueChange={setPartyId}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_all">All</SelectItem>
              {schema?.namespaces.map((ns) => (
                <SelectItem key={ns} value={ns}>
                  {ns}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Results: side-by-side */}
      {(filteredResults || unfilteredResults) && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ResultPanel
            title="Filtered Results"
            subtitle={
              filteredResults
                ? `${filteredResults.results_count} results | theme=${filteredResults.filters.theme ?? "all"} | fiabilite<=${filteredResults.filters.max_fiabilite} | ns=${filteredResults.filters.party_id ?? "all"}`
                : ""
            }
            results={filteredResults?.results ?? []}
            highlight
          />
          <ResultPanel
            title="Unfiltered Results"
            subtitle={
              unfilteredResults
                ? `${unfilteredResults.results_count} results | no metadata filters`
                : ""
            }
            results={unfilteredResults?.results ?? []}
          />
        </div>
      )}
    </div>
  );
}

function ResultPanel({
  title,
  subtitle,
  results,
  highlight,
}: {
  title: string;
  subtitle: string;
  results: SearchResult[];
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-4 ${highlight ? "border-blue-300 dark:border-blue-700" : "border-border"}`}
    >
      <h3 className="font-semibold">{title}</h3>
      <p className="text-muted-foreground mb-3 text-xs">{subtitle}</p>

      {results.length === 0 ? (
        <p className="text-muted-foreground py-8 text-center text-sm">
          No results
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {results.map((r, i) => (
            <ResultCard key={i} result={r} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

function ResultCard({ result, index }: { result: SearchResult; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const m = result.metadata;

  return (
    <button
      type="button"
      className="hover:bg-muted/50 cursor-pointer rounded-md border p-3 text-left transition-colors"
      onClick={() => setExpanded(!expanded)}
    >
      {/* Header row */}
      <div className="mb-1 flex flex-wrap items-center gap-1.5">
        <span className="bg-muted inline-flex size-5 items-center justify-center rounded-full text-[10px] font-bold">
          {index + 1}
        </span>
        <ScoreBadge score={result.score} />
        <FiabiliteBadge level={m.fiabilite as number} />
        <ThemeBadge theme={m.theme as string} />
        <SourceDocBadge sourceDoc={m.source_document as string} />
      </div>

      {/* Content preview */}
      <p className="text-sm leading-relaxed">
        {expanded ? result.content : result.content.slice(0, 200) + (result.content.length > 200 ? "..." : "")}
      </p>

      {/* Metadata details (expanded) */}
      {expanded && (
        <div className="bg-muted/30 mt-2 rounded border p-2">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider">
            Full Metadata
          </p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
            {Object.entries(m).map(([key, value]) => (
              <div key={key} className="flex gap-1">
                <span className="text-muted-foreground font-mono">{key}:</span>
                <span className="truncate font-mono">
                  {Array.isArray(value)
                    ? `[${(value as string[]).join(", ")}]`
                    : String(value ?? "null")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </button>
  );
}
