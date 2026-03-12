"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@components/ui/button";

interface DataConsistencyTabProps {
  secret: string;
  apiUrl: string;
}

interface DataConsistencyResponse {
  status: string;
  firestore: {
    parties: number;
    candidates: number;
    municipalities: number;
    candidates_with_website: number;
  };
  qdrant: {
    manifesto_points: number;
    manifesto_namespaces: string[];
    candidate_points: number;
    candidate_namespaces_count: number;
    candidate_municipalities: string[];
  };
  cross_references: {
    all_candidate_party_ids_in_firestore: boolean;
    all_candidate_munis_in_firestore: boolean;
    all_candidate_namespaces_in_firestore: boolean;
    all_manifesto_namespaces_in_firestore: boolean;
    orphan_candidate_namespaces: string[];
    orphan_manifesto_namespaces: string[];
    missing_party_ids: string[];
    missing_municipality_codes: string[];
  };
  metadata_quality: {
    sample_size: number;
    party_ids_populated_pct: number;
    municipality_code_populated_pct: number;
    theme_populated_pct: number;
    sub_theme_populated_pct: number;
    source_document_populated_pct: number;
    fiabilite_populated_pct: number;
  };
  issues: Array<{ severity: string; message: string }>;
}

function QualityBar({ label, pct }: { label: string; pct: number }) {
  const color =
    pct >= 90
      ? "bg-green-500"
      : pct >= 60
        ? "bg-yellow-500"
        : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-xs font-medium text-foreground">
          {pct.toFixed(1)}%
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted">
        <div
          className={`h-2 rounded-full ${color}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
}

export default function DataConsistencyTab({
  secret,
  apiUrl,
}: DataConsistencyTabProps) {
  const [data, setData] = useState<DataConsistencyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${apiUrl}/api/v1/admin/dashboard/data-consistency`,
        {
          headers: { "X-Admin-Secret": secret },
          cache: "no-store",
        },
      );
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const json: DataConsistencyResponse = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || "Failed to fetch data consistency");
    } finally {
      setLoading(false);
    }
  }, [secret, apiUrl]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">
          Loading data consistency...
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-6 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <Button
          size="sm"
          variant="outline"
          onClick={fetchData}
          className="mt-3"
        >
          Retry
        </Button>
      </div>
    );
  }

  if (!data) return null;

  const crossRefChecks = [
    {
      label: "All candidate party_ids exist in Firestore parties",
      pass: data.cross_references.all_candidate_party_ids_in_firestore,
      orphans: data.cross_references.missing_party_ids,
    },
    {
      label: "All candidate municipality_codes exist in Firestore municipalities",
      pass: data.cross_references.all_candidate_munis_in_firestore,
      orphans: data.cross_references.missing_municipality_codes,
    },
    {
      label: "All candidate namespaces exist in Firestore candidates",
      pass: data.cross_references.all_candidate_namespaces_in_firestore,
      orphans: data.cross_references.orphan_candidate_namespaces,
    },
    {
      label: "All manifesto namespaces exist in Firestore parties",
      pass: data.cross_references.all_manifesto_namespaces_in_firestore,
      orphans: data.cross_references.orphan_manifesto_namespaces,
    },
  ];

  const allCrossRefPass = crossRefChecks.every((c) => c.pass);

  return (
    <div className="space-y-6">
      {/* Header with refresh */}
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">
          Status:{" "}
          <span
            className={
              data.status === "consistent"
                ? "text-green-400 font-medium"
                : "text-yellow-400 font-medium"
            }
          >
            {data.status}
          </span>
        </span>
        <Button
          size="sm"
          variant="ghost"
          onClick={fetchData}
          className="h-8 gap-1.5 text-xs"
        >
          <RefreshCw className="size-3.5" />
          Refresh
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Firestore */}
        <div className="rounded-lg border border-border-subtle bg-card p-4">
          <div className="text-sm font-semibold text-foreground mb-3">
            Firestore
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Parties</span>
              <span className="text-lg font-bold text-foreground">
                {data.firestore.parties}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Candidates</span>
              <span className="text-lg font-bold text-foreground">
                {data.firestore.candidates}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Municipalities
              </span>
              <span className="text-lg font-bold text-foreground">
                {data.firestore.municipalities}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                With website
              </span>
              <span className="text-lg font-bold text-foreground">
                {data.firestore.candidates_with_website}
              </span>
            </div>
          </div>
        </div>

        {/* Qdrant Manifestos */}
        <div className="rounded-lg border border-border-subtle bg-card p-4">
          <div className="text-sm font-semibold text-foreground mb-3">
            Qdrant Manifestos
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Points</span>
              <span className="text-lg font-bold text-foreground">
                {data.qdrant.manifesto_points.toLocaleString()}
              </span>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">
                Namespaces ({data.qdrant.manifesto_namespaces.length})
              </span>
              <div className="mt-1 flex flex-wrap gap-1">
                {data.qdrant.manifesto_namespaces.map((ns) => (
                  <span
                    key={ns}
                    className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
                  >
                    {ns}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Qdrant Candidates */}
        <div className="rounded-lg border border-border-subtle bg-card p-4">
          <div className="text-sm font-semibold text-foreground mb-3">
            Qdrant Candidates
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Points</span>
              <span className="text-lg font-bold text-foreground">
                {data.qdrant.candidate_points.toLocaleString()}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Namespaces</span>
              <span className="text-lg font-bold text-foreground">
                {data.qdrant.candidate_namespaces_count}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Municipalities
              </span>
              <span className="text-lg font-bold text-foreground">
                {data.qdrant.candidate_municipalities.length}
              </span>
            </div>
          </div>
        </div>

        {/* Cross-reference status */}
        <div className="rounded-lg border border-border-subtle bg-card p-4">
          <div className="text-sm font-semibold text-foreground mb-3">
            Cross-Reference
          </div>
          <div className="flex flex-col items-center justify-center py-2">
            {allCrossRefPass ? (
              <>
                <span className="bg-green-500/20 text-green-400 text-xs px-2 py-0.5 rounded-full">
                  All checks pass
                </span>
                <CheckCircle2 className="mt-2 size-8 text-green-400" />
              </>
            ) : (
              <>
                <span className="bg-red-500/20 text-red-400 text-xs px-2 py-0.5 rounded-full">
                  Issues detected
                </span>
                <XCircle className="mt-2 size-8 text-red-400" />
              </>
            )}
          </div>
        </div>
      </div>

      {/* Cross-Reference Checks */}
      <section>
        <div className="mb-3 flex items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Cross-Reference Checks
          </span>
          <div className="flex-1 border-t border-border-subtle" />
        </div>
        <div className="space-y-2">
          {crossRefChecks.map((check, i) => (
            <div
              key={i}
              className="rounded-lg border border-border-subtle bg-card p-3"
            >
              <div className="flex items-center gap-2">
                {check.pass ? (
                  <CheckCircle2 className="size-4 shrink-0 text-green-400" />
                ) : (
                  <XCircle className="size-4 shrink-0 text-red-400" />
                )}
                <span className="text-sm text-foreground">{check.label}</span>
                {check.pass ? (
                  <span className="ml-auto bg-green-500/20 text-green-400 text-xs px-2 py-0.5 rounded-full">
                    pass
                  </span>
                ) : (
                  <span className="ml-auto bg-red-500/20 text-red-400 text-xs px-2 py-0.5 rounded-full">
                    fail
                  </span>
                )}
              </div>
              {!check.pass && check.orphans.length > 0 && (
                <div className="mt-2 ml-6">
                  <span className="text-xs text-muted-foreground">
                    Missing/orphaned:
                  </span>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {check.orphans.map((id) => (
                      <span
                        key={id}
                        className="rounded bg-red-500/10 px-1.5 py-0.5 text-xs text-red-400"
                      >
                        {id}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Metadata Quality */}
      <section>
        <div className="mb-3 flex items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Metadata Quality
          </span>
          <span className="text-xs text-muted-foreground">
            (sample: {data.metadata_quality.sample_size} points)
          </span>
          <div className="flex-1 border-t border-border-subtle" />
        </div>
        <div className="rounded-lg border border-border-subtle bg-card p-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <QualityBar
              label="party_ids"
              pct={data.metadata_quality.party_ids_populated_pct}
            />
            <QualityBar
              label="municipality_code"
              pct={data.metadata_quality.municipality_code_populated_pct}
            />
            <QualityBar
              label="theme"
              pct={data.metadata_quality.theme_populated_pct}
            />
            <QualityBar
              label="sub_theme"
              pct={data.metadata_quality.sub_theme_populated_pct}
            />
            <QualityBar
              label="source_document"
              pct={data.metadata_quality.source_document_populated_pct}
            />
            <QualityBar
              label="fiabilite"
              pct={data.metadata_quality.fiabilite_populated_pct}
            />
          </div>
        </div>
      </section>

      {/* Issues */}
      {data.issues.length > 0 && (
        <section>
          <div className="mb-3 flex items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Issues
            </span>
            <div className="flex-1 border-t border-border-subtle" />
          </div>
          <div className="space-y-2">
            {data.issues.map((issue, i) => {
              const colors =
                issue.severity === "critical"
                  ? "border-red-500/30 bg-red-500/10 text-red-400"
                  : issue.severity === "warning"
                    ? "border-yellow-500/30 bg-yellow-500/10 text-yellow-400"
                    : "border-blue-500/30 bg-blue-500/10 text-blue-400";
              const badge =
                issue.severity === "critical"
                  ? "bg-red-500/20 text-red-400"
                  : issue.severity === "warning"
                    ? "bg-yellow-500/20 text-yellow-400"
                    : "bg-blue-500/20 text-blue-400";
              return (
                <div
                  key={i}
                  className={`rounded-lg border p-3 ${colors}`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${badge}`}
                    >
                      {issue.severity}
                    </span>
                    <span className="text-sm">{issue.message}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
