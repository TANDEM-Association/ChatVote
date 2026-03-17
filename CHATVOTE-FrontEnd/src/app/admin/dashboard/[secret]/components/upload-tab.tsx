"use client";

import {
  type ChangeEvent,
  type DragEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { Badge } from "@components/ui/badge";
import { Button } from "@components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@components/ui/card";
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardPaste,
  Eye,
  FileText,
  Loader2,
  RefreshCw,
  Search,
  Send,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type JobStage =
  | "pending"
  | "uploading"
  | "extracting"
  | "classifying"
  | "chunking"
  | "embedding"
  | "indexing"
  | "preview"
  | "done"
  | "error";

interface AssignmentInfo {
  target_name: string;
  target_id: string;
  target_type: string;
  confidence: number;
}

interface ChunkMetadataInfo {
  source_document?: string;
  fiabilite?: number;
  theme?: string;
  sub_theme?: string;
  url?: string;
  namespace?: string;
  party_name?: string;
  candidate_name?: string;
  [key: string]: unknown;
}

interface ChunkPreview {
  index: number;
  content: string;
  length: number;
  metadata?: ChunkMetadataInfo;
}

interface PreviewData {
  text_length: number;
  text_preview: string;
  chunks_count: number;
  chunk_previews: ChunkPreview[];
  auto_assignment: AssignmentInfo | null;
  error?: string;
}

interface JobStatus {
  job_id: string;
  filename: string;
  status: JobStage;
  progress: number;
  assigned_to?: AssignmentInfo | null;
  collection?: string;
  chunks_indexed?: number;
  error?: string;
  preview?: PreviewData;
}

interface Target {
  type: "party" | "candidate";
  id: string;
  name: string;
  abbreviation?: string | null;
  municipality?: string;
  party_ids?: string[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ACCEPTED_TYPES = ["application/pdf", "text/plain"];
const ACCEPTED_EXTENSIONS = [".pdf", ".txt"];

const POLL_INTERVAL_MS = 2000;

const STAGE_ORDER: JobStage[] = [
  "pending",
  "uploading",
  "extracting",
  "classifying",
  "chunking",
  "embedding",
  "indexing",
  "done",
];

function stageProgress(stage: JobStage): number {
  if (stage === "preview") return 60;
  const idx = STAGE_ORDER.indexOf(stage);
  if (idx === -1) return 0;
  return Math.round((idx / (STAGE_ORDER.length - 1)) * 100);
}

function stageLabel(stage: JobStage): string {
  const labels: Record<JobStage, string> = {
    pending: "Pending",
    uploading: "Uploading...",
    extracting: "Extracting text...",
    classifying: "Classifying...",
    chunking: "Chunking...",
    embedding: "Embedding...",
    indexing: "Indexing...",
    preview: "Ready for review",
    done: "Done",
    error: "Error",
  };
  return labels[stage];
}

// ---------------------------------------------------------------------------
// Source selector — searchable combobox with candidate city + ID display
// ---------------------------------------------------------------------------

function SourceSelector({
  value,
  onChange,
  partyTargets,
  candidateTargets,
  targetsLoading,
  autoLabel,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  partyTargets: Target[];
  candidateTargets: Target[];
  targetsLoading: boolean;
  autoLabel?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Focus input when opened
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const lowerQuery = query.toLowerCase();

  const filteredParties = useMemo(
    () =>
      partyTargets.filter(
        (t) =>
          !lowerQuery ||
          t.name.toLowerCase().includes(lowerQuery) ||
          (t.abbreviation && t.abbreviation.toLowerCase().includes(lowerQuery)) ||
          t.id.toLowerCase().includes(lowerQuery),
      ),
    [partyTargets, lowerQuery],
  );

  const filteredCandidates = useMemo(
    () =>
      candidateTargets.filter(
        (t) =>
          !lowerQuery ||
          t.name.toLowerCase().includes(lowerQuery) ||
          (t.municipality && t.municipality.toLowerCase().includes(lowerQuery)) ||
          t.id.toLowerCase().includes(lowerQuery),
      ),
    [candidateTargets, lowerQuery],
  );

  // Resolve display label for current value
  const displayLabel = useMemo(() => {
    if (value === "auto") return autoLabel ?? "Auto-detect";
    const [type, id] = value.split(":", 2);
    const all = [...partyTargets, ...candidateTargets];
    const t = all.find((t) => t.type === type && t.id === id);
    if (!t) return value;
    if (t.type === "candidate") {
      return `${t.name}${t.municipality ? ` — ${t.municipality}` : ""}`;
    }
    return `${t.name}${t.abbreviation ? ` (${t.abbreviation})` : ""}`;
  }, [value, partyTargets, candidateTargets, autoLabel]);

  function select(val: string) {
    onChange(val);
    setOpen(false);
    setQuery("");
  }

  const hasResults =
    filteredParties.length > 0 || filteredCandidates.length > 0;

  return (
    <div ref={containerRef} className={`relative ${open ? "z-50" : ""} ${className ?? ""}`}>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus:ring-ring flex h-9 w-full items-center justify-between gap-2 rounded-md border px-3 py-1.5 text-sm focus:ring-1 focus:outline-none"
      >
        <span className="truncate">{displayLabel}</span>
        <ChevronDown className="text-muted-foreground size-3.5 shrink-0" />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="bg-card text-card-foreground absolute z-50 mt-1 w-full min-w-[280px] overflow-hidden rounded-lg border shadow-2xl ring-1 ring-white/10">
          {/* Search input */}
          <div className="bg-card flex items-center gap-2 border-b border-white/10 px-3 py-2">
            <Search className="text-muted-foreground size-3.5 shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search party or candidate..."
              className="bg-transparent text-sm placeholder:text-muted-foreground w-full outline-none"
            />
          </div>

          <div className="max-h-[300px] overflow-y-auto p-1">
            {/* Auto-detect option */}
            {(!lowerQuery ||
              "auto".includes(lowerQuery) ||
              "detect".includes(lowerQuery)) && (
              <button
                type="button"
                onClick={() => select("auto")}
                className="hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm"
              >
                {value === "auto" && (
                  <Check className="text-primary size-3.5 shrink-0" />
                )}
                <span className={value === "auto" ? "" : "pl-5"}>
                  {autoLabel ?? "Auto-detect"}
                </span>
              </button>
            )}

            {/* Parties */}
            {filteredParties.length > 0 && (
              <>
                <div className="text-muted-foreground px-2 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider">
                  Parties
                </div>
                {filteredParties.map((t) => {
                  const val = `party:${t.id}`;
                  const selected = value === val;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => select(val)}
                      className="hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm"
                    >
                      {selected && (
                        <Check className="text-primary size-3.5 shrink-0" />
                      )}
                      <span className={selected ? "" : "pl-5"}>
                        {t.name}
                        {t.abbreviation && (
                          <span className="text-muted-foreground ml-1">
                            ({t.abbreviation})
                          </span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </>
            )}

            {/* Candidates */}
            {filteredCandidates.length > 0 && (
              <>
                <div className="text-muted-foreground px-2 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider">
                  Candidates
                </div>
                {filteredCandidates.map((t) => {
                  const val = `candidate:${t.id}`;
                  const selected = value === val;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => select(val)}
                      className="hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm"
                    >
                      {selected && (
                        <Check className="text-primary size-3.5 shrink-0" />
                      )}
                      <span className={`min-w-0 ${selected ? "" : "pl-5"}`}>
                        <span className="font-medium">{t.name}</span>
                        {t.municipality && (
                          <span className="text-muted-foreground ml-1.5">
                            — {t.municipality}
                          </span>
                        )}
                        <span className="text-muted-foreground/60 ml-1.5 text-xs">
                          ({t.id})
                        </span>
                      </span>
                    </button>
                  );
                })}
              </>
            )}

            {/* Loading / no results */}
            {targetsLoading && (
              <div className="text-muted-foreground flex items-center gap-2 px-2 py-3 text-sm">
                <Loader2 className="size-3.5 animate-spin" />
                Loading targets...
              </div>
            )}

            {!targetsLoading && !hasResults && lowerQuery && (
              <div className="text-muted-foreground px-2 py-3 text-center text-sm">
                No results for &ldquo;{query}&rdquo;
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab component
// ---------------------------------------------------------------------------

type InputMode = "file" | "text";

export default function UploadTab({
  secret,
  apiUrl,
  active: _active,
}: {
  secret: string;
  apiUrl: string;
  active?: boolean;
}) {
  const [jobs, setJobs] = useState<Map<string, JobStatus>>(new Map());
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [targets, setTargets] = useState<Target[]>([]);
  const [targetsLoading, setTargetsLoading] = useState(true);

  // Global source assignment (applies to all new uploads)
  const [globalSource, setGlobalSource] = useState("auto");

  // Per-job manual override selection (job_id -> "type:id")
  const [manualOverrides, setManualOverrides] = useState<Map<string, string>>(
    new Map(),
  );

  // Input mode toggle
  const [inputMode, setInputMode] = useState<InputMode>("file");

  // Text paste state
  const [pastedText, setPastedText] = useState("");
  const [pasteTitle, setPasteTitle] = useState("");

  // Source metadata (URL for uncrawled sites, source type)
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceType, setSourceType] = useState("");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dragCounterRef = useRef(0);

  // ---- Load available targets on mount ----

  useEffect(() => {
    async function loadTargets() {
      try {
        const resp = await fetch(`${apiUrl}/api/v1/admin/upload-targets`, {
          headers: { "X-Upload-Secret": secret },
        });
        if (resp.ok) {
          const data = await resp.json();
          setTargets(data.targets || []);
        }
      } catch {
        // Non-critical
      } finally {
        setTargetsLoading(false);
      }
    }
    loadTargets();
  }, [secret, apiUrl]);

  // ---- Polling for job status updates ----

  const activeJobIds = useRef<Set<string>>(new Set());

  const pollStatuses = useCallback(async () => {
    if (activeJobIds.current.size === 0) return;

    try {
      const resp = await fetch(`${apiUrl}/api/v1/admin/upload-status`, {
        headers: { "X-Upload-Secret": secret },
      });

      if (!resp.ok) return;

      const data = (await resp.json()) as {
        jobs: Record<string, JobStatus>;
      };

      setJobs((prev) => {
        const next = new Map(prev);
        for (const [id, status] of Object.entries(data.jobs)) {
          if (next.has(id)) {
            next.set(id, { ...next.get(id)!, ...status, job_id: id });
          }
          if (["done", "error", "preview"].includes(status.status)) {
            activeJobIds.current.delete(id);
          }
        }
        return next;
      });
    } catch {
      // Silently ignore poll errors
    }
  }, [secret, apiUrl]);

  useEffect(() => {
    pollingRef.current = setInterval(pollStatuses, POLL_INTERVAL_MS);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [pollStatuses]);

  // ---- File validation ----

  const isValidFile = useCallback((file: File): boolean => {
    if (ACCEPTED_TYPES.includes(file.type)) return true;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    return ACCEPTED_EXTENSIONS.includes(ext);
  }, []);

  // ---- Helper: add jobs from API response ----

  const addJobsFromResponse = useCallback(
    (
      data: {
        jobs: Array<{
          job_id: string;
          filename: string;
          status: JobStage;
          error?: string;
          preview?: PreviewData;
        }>;
      },
    ) => {
      setJobs((prev) => {
        const next = new Map(prev);
        for (const job of data.jobs) {
          next.set(job.job_id, {
            job_id: job.job_id,
            filename: job.filename,
            status: job.status,
            progress: stageProgress(job.status),
            preview: job.preview,
            assigned_to: job.preview?.auto_assignment || null,
            error: job.error ?? job.preview?.error,
          });
          if (!["preview", "done", "error"].includes(job.status)) {
            activeJobIds.current.add(job.job_id);
          }
          // Apply global source as default override
          if (globalSource !== "auto") {
            setManualOverrides((prev) => {
              const next = new Map(prev);
              next.set(job.job_id, globalSource);
              return next;
            });
          }
        }
        return next;
      });
    },
    [globalSource],
  );

  // ---- File upload handler (preview mode) ----

  const handleUpload = useCallback(
    async (files: File[]) => {
      const valid = files.filter(isValidFile);
      if (valid.length === 0) {
        setUploadError("No valid files. Only PDF and TXT are accepted.");
        return;
      }

      setUploadError(null);
      setIsUploading(true);

      try {
        const formData = new FormData();
        formData.append("mode", "preview");
        if (sourceUrl.trim()) formData.append("source_url", sourceUrl.trim());
        if (sourceType.trim()) formData.append("source_type", sourceType.trim());
        valid.forEach((f) => formData.append("files", f));

        const resp = await fetch(`${apiUrl}/api/v1/admin/upload`, {
          method: "POST",
          headers: { "X-Upload-Secret": secret },
          body: formData,
        });

        if (!resp.ok) {
          const text = await resp.text();
          setUploadError(`Upload failed (${resp.status}): ${text}`);
          return;
        }

        addJobsFromResponse(await resp.json());
      } catch (err) {
        setUploadError(
          `Network error: ${err instanceof Error ? err.message : "Unknown error"}`,
        );
      } finally {
        setIsUploading(false);
      }
    },
    [secret, apiUrl, isValidFile, addJobsFromResponse],
  );

  // ---- Text paste handler ----

  const handleTextSubmit = useCallback(async () => {
    const text = pastedText.trim();
    if (text.length < 50) {
      setUploadError("Text is too short (minimum 50 characters).");
      return;
    }

    setUploadError(null);
    setIsUploading(true);

    try {
      const resp = await fetch(`${apiUrl}/api/v1/admin/upload-text`, {
        method: "POST",
        headers: {
          "X-Upload-Secret": secret,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text,
          title: pasteTitle.trim() || "Pasted text",
          mode: "preview",
          ...(sourceUrl.trim() && { source_url: sourceUrl.trim() }),
          ...(sourceType.trim() && { source_type: sourceType.trim() }),
        }),
      });

      if (!resp.ok) {
        const t = await resp.text();
        setUploadError(`Upload failed (${resp.status}): ${t}`);
        return;
      }

      addJobsFromResponse(await resp.json());
      setPastedText("");
      setPasteTitle("");
    } catch (err) {
      setUploadError(
        `Network error: ${err instanceof Error ? err.message : "Unknown error"}`,
      );
    } finally {
      setIsUploading(false);
    }
  }, [secret, apiUrl, pastedText, pasteTitle, addJobsFromResponse]);

  // ---- Confirm handler ----

  const handleConfirm = useCallback(
    async (jobId: string) => {
      const override = manualOverrides.get(jobId) || globalSource;
      let body: Record<string, string> = {};
      if (override && override !== "auto") {
        const [targetType, targetId] = override.split(":", 2);
        body = { target_type: targetType, target_id: targetId };
      }
      if (sourceUrl.trim()) body.source_url = sourceUrl.trim();
      if (sourceType.trim()) body.source_type = sourceType.trim();

      setJobs((prev) => {
        const next = new Map(prev);
        const job = next.get(jobId);
        if (job) {
          next.set(jobId, { ...job, status: "extracting", progress: 10 });
        }
        return next;
      });
      activeJobIds.current.add(jobId);

      try {
        const resp = await fetch(
          `${apiUrl}/api/v1/admin/upload-confirm/${jobId}`,
          {
            method: "POST",
            headers: {
              "X-Upload-Secret": secret,
              "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
          },
        );

        if (!resp.ok) {
          const text = await resp.text();
          setJobs((prev) => {
            const next = new Map(prev);
            const job = next.get(jobId);
            if (job) {
              next.set(jobId, {
                ...job,
                status: "error",
                error: `Confirm failed: ${text}`,
              });
            }
            return next;
          });
          activeJobIds.current.delete(jobId);
        }
      } catch (err) {
        setJobs((prev) => {
          const next = new Map(prev);
          const job = next.get(jobId);
          if (job) {
            next.set(jobId, {
              ...job,
              status: "error",
              error: `Network error: ${err instanceof Error ? err.message : "Unknown"}`,
            });
          }
          return next;
        });
        activeJobIds.current.delete(jobId);
      }
    },
    [secret, apiUrl, manualOverrides, globalSource, sourceUrl, sourceType],
  );

  // ---- Confirm all previewed jobs ----

  const handleConfirmAll = useCallback(async () => {
    const previewJobs = Array.from(jobs.values()).filter(
      (j) => j.status === "preview",
    );
    await Promise.all(previewJobs.map((j) => handleConfirm(j.job_id)));
  }, [jobs, handleConfirm]);

  // ---- Remove job ----

  const handleRemove = useCallback((jobId: string) => {
    setJobs((prev) => {
      const next = new Map(prev);
      next.delete(jobId);
      return next;
    });
    activeJobIds.current.delete(jobId);
    setManualOverrides((prev) => {
      const next = new Map(prev);
      next.delete(jobId);
      return next;
    });
  }, []);

  // ---- Drag & drop handlers ----

  const onDragEnter = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current += 1;
    if (dragCounterRef.current === 1) setIsDragging(true);
  }, []);

  const onDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current === 0) setIsDragging(false);
  }, []);

  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounterRef.current = 0;
      setIsDragging(false);

      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) handleUpload(files);
    },
    [handleUpload],
  );

  const onFileChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files ? Array.from(e.target.files) : [];
      if (files.length > 0) handleUpload(files);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [handleUpload],
  );

  // ---- Derived state ----

  const jobList = Array.from(jobs.values());
  const previewJobs = jobList.filter((j) => j.status === "preview");
  const processingJobs = jobList.filter(
    (j) => !["preview", "done", "error"].includes(j.status),
  );
  const completedJobs = jobList.filter(
    (j) => j.status === "done" || j.status === "error",
  );

  const partyTargets = useMemo(
    () => targets.filter((t) => t.type === "party"),
    [targets],
  );
  const candidateTargets = useMemo(
    () => targets.filter((t) => t.type === "candidate"),
    [targets],
  );

  // Resolve global source label for display
  const globalSourceLabel = useMemo(() => {
    if (globalSource === "auto") return null;
    const [type, id] = globalSource.split(":", 2);
    const t = targets.find((t) => t.type === type && t.id === id);
    return t ? t.name : globalSource;
  }, [globalSource, targets]);

  // ---- Render ----

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold">Document Upload</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Upload files or paste text, configure source assignment, preview
          chunks, then index into Qdrant.
        </p>
      </div>

      {/* Global source assignment */}
      <Card className="relative z-10 overflow-visible">
        <CardContent className="flex items-end gap-4 overflow-visible pt-6">
          <div className="flex-1 space-y-1.5">
            <label className="text-sm font-medium">
              Default source assignment
            </label>
            <p className="text-muted-foreground text-xs">
              Pre-select a target for all uploads. Can be overridden per file.
            </p>
            <SourceSelector
              value={globalSource}
              onChange={setGlobalSource}
              partyTargets={partyTargets}
              candidateTargets={candidateTargets}
              targetsLoading={targetsLoading}
              autoLabel="Auto-detect from content"
            />
          </div>
          {globalSourceLabel && (
            <Badge variant="secondary" className="mb-1 shrink-0">
              Default: {globalSourceLabel}
            </Badge>
          )}
        </CardContent>
      </Card>

      {/* Source metadata (URL + type) */}
      <Card>
        <CardContent className="grid grid-cols-2 gap-4 pt-6">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="source-url">
              Source URL
            </label>
            <input
              id="source-url"
              type="url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://example.com/candidate-page"
              className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus:ring-ring flex h-9 w-full rounded-md border px-3 py-1.5 text-sm focus-within:outline-none focus:ring-1"
            />
            <p className="text-muted-foreground text-xs">
              Optional. URL of the source website (e.g. a site you couldn&apos;t crawl).
            </p>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="source-type">
              Source type
            </label>
            <select
              id="source-type"
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              className="border-input bg-background ring-offset-background focus:ring-ring flex h-9 w-full rounded-md border px-3 py-1.5 text-sm focus-within:outline-none focus:ring-1"
            >
              <option value="">Default (uploaded_document)</option>
              <option value="profession_de_foi">Profession de foi</option>
              <option value="election_manifesto">Programme / Manifeste</option>
              <option value="candidate_website">Site candidat</option>
              <option value="candidate_website_programme">Site candidat - Programme</option>
              <option value="candidate_website_about">Site candidat - À propos</option>
              <option value="party_website">Site parti</option>
              <option value="candidate_website_blog">Blog / Actualité</option>
            </select>
            <p className="text-muted-foreground text-xs">
              Determines the fiabilité level of indexed chunks.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Input mode toggle */}
      <div className="flex gap-1 rounded-lg border p-1">
        <button
          type="button"
          onClick={() => setInputMode("file")}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            inputMode === "file"
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <UploadCloud className="size-3.5" />
          File Upload
        </button>
        <button
          type="button"
          onClick={() => setInputMode("text")}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            inputMode === "text"
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <ClipboardPaste className="size-3.5" />
          Paste Text
        </button>
      </div>

      {/* File drop zone */}
      {inputMode === "file" && (
        <div
          onDragEnter={onDragEnter}
          onDragLeave={onDragLeave}
          onDragOver={onDragOver}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-10 transition-colors ${
            isDragging
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/50 hover:bg-muted/30"
          }`}
        >
          <UploadCloud
            className={`size-10 ${isDragging ? "text-primary" : "text-muted-foreground"}`}
          />
          <p className="text-muted-foreground text-center text-sm">
            {isDragging ? (
              <span className="text-primary font-semibold">
                Drop files here
              </span>
            ) : (
              <>
                Drop files here or{" "}
                <span className="text-primary font-semibold underline underline-offset-2">
                  click to browse
                </span>
              </>
            )}
          </p>
          <p className="text-muted-foreground/70 text-xs">
            PDF, TXT — files are previewed before indexing
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,application/pdf,text/plain"
            multiple
            className="hidden"
            onChange={onFileChange}
          />
        </div>
      )}

      {/* Text paste area */}
      {inputMode === "text" && (
        <Card>
          <CardContent className="space-y-3 pt-6">
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="paste-title">
                Title
              </label>
              <input
                id="paste-title"
                type="text"
                value={pasteTitle}
                onChange={(e) => setPasteTitle(e.target.value)}
                placeholder="e.g. Programme municipal Renaissance Lyon"
                className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus:ring-ring flex h-9 w-full rounded-md border px-3 py-1.5 text-sm focus-within:outline-none focus:ring-1"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="paste-text">
                Content
              </label>
              <textarea
                id="paste-text"
                value={pastedText}
                onChange={(e) => setPastedText(e.target.value)}
                placeholder="Paste document text here..."
                rows={10}
                className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus:ring-ring flex w-full rounded-md border px-3 py-2 text-sm leading-relaxed focus-within:outline-none focus:ring-1"
              />
              <div className="flex items-center justify-between">
                <p className="text-muted-foreground text-xs">
                  {pastedText.length.toLocaleString()} characters
                  {pastedText.length < 50 && pastedText.length > 0 && (
                    <span className="text-amber-500">
                      {" "}
                      — minimum 50 required
                    </span>
                  )}
                </p>
                <Button
                  onClick={handleTextSubmit}
                  size="sm"
                  className="gap-1.5"
                  disabled={pastedText.trim().length < 50 || isUploading}
                >
                  <Eye className="size-3.5" />
                  Preview
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Upload error */}
      {uploadError && (
        <div className="border-destructive/30 bg-destructive/5 text-destructive rounded-lg border px-4 py-3 text-sm">
          {uploadError}
        </div>
      )}

      {/* Uploading spinner */}
      {isUploading && (
        <div className="text-muted-foreground flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin" />
          Analyzing content...
        </div>
      )}

      {/* Preview section */}
      {previewJobs.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              Review &amp; Configure ({previewJobs.length} item
              {previewJobs.length > 1 ? "s" : ""})
            </h2>
            <Button
              onClick={handleConfirmAll}
              size="sm"
              className="gap-1.5"
            >
              <Send className="size-3.5" />
              Index All
            </Button>
          </div>

          {previewJobs.map((job) => (
            <PreviewCard
              key={job.job_id}
              job={job}
              partyTargets={partyTargets}
              candidateTargets={candidateTargets}
              targetsLoading={targetsLoading}
              selectedOverride={
                manualOverrides.get(job.job_id) || globalSource
              }
              onOverrideChange={(value) =>
                setManualOverrides((prev) => {
                  const next = new Map(prev);
                  next.set(job.job_id, value);
                  return next;
                })
              }
              onConfirm={() => handleConfirm(job.job_id)}
              onRemove={() => handleRemove(job.job_id)}
            />
          ))}
        </div>
      )}

      {/* Processing jobs */}
      {processingJobs.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Processing</h2>
          <div className="border-border overflow-hidden rounded-xl border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-border bg-muted/50 text-muted-foreground border-b text-left text-xs tracking-wider uppercase">
                  <th className="px-4 py-2.5">File</th>
                  <th className="px-4 py-2.5">Assigned To</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5 text-right">Chunks</th>
                </tr>
              </thead>
              <tbody>
                {processingJobs.map((job) => (
                  <JobRow key={job.job_id} job={job} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Completed jobs */}
      {completedJobs.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Completed</h2>
          <div className="border-border overflow-hidden rounded-xl border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-border bg-muted/50 text-muted-foreground border-b text-left text-xs tracking-wider uppercase">
                  <th className="px-4 py-2.5">File</th>
                  <th className="px-4 py-2.5">Assigned To</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5 text-right">Chunks</th>
                  <th className="w-10 px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {completedJobs.map((job) => (
                  <JobRow
                    key={job.job_id}
                    job={job}
                    onRetry={() => handleRemove(job.job_id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Preview card — shows extraction results + source config before indexing
// ---------------------------------------------------------------------------

function PreviewCard({
  job,
  partyTargets,
  candidateTargets,
  targetsLoading,
  selectedOverride,
  onOverrideChange,
  onConfirm,
  onRemove,
}: {
  job: JobStatus;
  partyTargets: Target[];
  candidateTargets: Target[];
  targetsLoading: boolean;
  selectedOverride: string;
  onOverrideChange: (value: string) => void;
  onConfirm: () => void;
  onRemove: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const preview = job.preview;
  const autoAssignment = preview?.auto_assignment;

  // Compute effective assignment for metadata display
  const effectiveOverride = useMemo(() => {
    if (selectedOverride && selectedOverride !== "auto") {
      const [tType, tId] = selectedOverride.split(":", 2);
      const targets = tType === "party" ? partyTargets : candidateTargets;
      const match = targets.find((t) => `${t.type}:${t.id}` === selectedOverride);
      const name = match ? match.name : tId;
      return { type: tType, id: tId, name };
    }
    if (autoAssignment) {
      return {
        type: autoAssignment.target_type,
        id: autoAssignment.target_id,
        name: autoAssignment.target_name,
      };
    }
    return null;
  }, [selectedOverride, autoAssignment, partyTargets, candidateTargets]);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <FileText className="text-muted-foreground size-5 shrink-0" />
            <div className="min-w-0">
              <CardTitle className="truncate text-base">
                {job.filename}
              </CardTitle>
              {preview && (
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {preview.text_length.toLocaleString()} chars extracted
                  &middot; {preview.chunks_count} chunks
                </p>
              )}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            <Button
              variant="ghost"
              size="sm"
              onClick={onRemove}
              className="text-muted-foreground hover:text-destructive h-7 px-2"
            >
              <X className="size-3.5" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Auto-detection result */}
        {autoAssignment && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Auto-detected:</span>
            <Badge variant="secondary">
              {autoAssignment.target_type === "party" ? "Party" : "Candidate"}
            </Badge>
            <span className="font-medium">{autoAssignment.target_name}</span>
            <span className="text-muted-foreground text-xs">
              ({Math.round(autoAssignment.confidence * 100)}% confidence)
            </span>
          </div>
        )}

        {!autoAssignment && preview && !preview.error && (
          <div className="flex items-center gap-2 text-sm text-amber-600">
            <XCircle className="size-3.5" />
            Could not auto-detect source — please select manually
          </div>
        )}

        {preview?.error && (
          <div className="text-destructive flex items-center gap-2 text-sm">
            <XCircle className="size-3.5" />
            {preview.error}
          </div>
        )}

        {/* Source override selector */}
        <div className="flex items-end gap-3">
          <div className="flex-1 space-y-1.5">
            <label className="text-sm font-medium">Assign to</label>
            <SourceSelector
              value={selectedOverride}
              onChange={onOverrideChange}
              partyTargets={partyTargets}
              candidateTargets={candidateTargets}
              targetsLoading={targetsLoading}
              autoLabel={
                autoAssignment
                  ? `Auto: ${autoAssignment.target_name}`
                  : "Auto-detect (failed)"
              }
            />
          </div>

          <Button
            onClick={onConfirm}
            size="sm"
            className="h-9 gap-1.5"
            disabled={!autoAssignment && selectedOverride === "auto"}
          >
            <Send className="size-3.5" />
            Index
          </Button>
        </div>

        {/* Expandable preview */}
        {preview &&
          preview.chunk_previews &&
          preview.chunk_previews.length > 0 && (
            <div>
              <button
                type="button"
                onClick={() => setExpanded(!expanded)}
                className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs transition-colors"
              >
                {expanded ? (
                  <ChevronDown className="size-3" />
                ) : (
                  <ChevronRight className="size-3" />
                )}
                <Eye className="size-3" />
                Preview chunks ({preview.chunks_count} total)
              </button>

              {expanded && (
                <div className="mt-2 space-y-2">
                  {/* Text preview */}
                  <div className="bg-muted/50 rounded-lg border p-3">
                    <p className="text-muted-foreground mb-1 text-xs font-medium uppercase">
                      Extracted text (first 500 chars)
                    </p>
                    <p className="whitespace-pre-wrap text-xs leading-relaxed">
                      {preview.text_preview}
                    </p>
                  </div>

                  {/* Chunk previews */}
                  <div className="space-y-1.5">
                    <p className="text-muted-foreground text-xs font-medium uppercase">
                      Sample chunks (first 5 of {preview.chunks_count})
                    </p>
                    {preview.chunk_previews.map((chunk) => (
                      <div
                        key={chunk.index}
                        className="bg-muted/30 rounded-lg border px-3 py-2"
                      >
                        <div className="text-muted-foreground mb-1 flex items-center justify-between text-[10px]">
                          <span>Chunk #{chunk.index}</span>
                          <span>{chunk.length} chars</span>
                        </div>
                        <p className="whitespace-pre-wrap text-xs leading-relaxed">
                          {chunk.content}
                        </p>
                        {chunk.metadata && (
                          <div className="mt-2 flex flex-wrap gap-1.5 border-t border-white/5 pt-2">
                            {chunk.metadata.source_document && (
                              <Badge variant="outline" className="text-[10px]">
                                source: {chunk.metadata.source_document}
                              </Badge>
                            )}
                            {chunk.metadata.fiabilite != null && (
                              <Badge variant="outline" className="text-[10px]">
                                fiabilité: {chunk.metadata.fiabilite}
                              </Badge>
                            )}
                            {chunk.metadata.theme && (
                              <Badge variant="secondary" className="text-[10px]">
                                {chunk.metadata.theme}
                              </Badge>
                            )}
                            {chunk.metadata.sub_theme && (
                              <Badge variant="secondary" className="text-[10px]">
                                {chunk.metadata.sub_theme}
                              </Badge>
                            )}
                            {chunk.metadata.url && (
                              <Badge variant="outline" className="text-[10px]">
                                url: {chunk.metadata.url}
                              </Badge>
                            )}
                            {(effectiveOverride?.id || chunk.metadata.namespace) && (
                              <Badge variant="outline" className="text-[10px]">
                                ns: {effectiveOverride?.id ?? chunk.metadata.namespace}
                              </Badge>
                            )}
                            {effectiveOverride?.type === "party" ? (
                              <Badge variant="outline" className="text-[10px]">
                                party: {effectiveOverride.name}
                              </Badge>
                            ) : chunk.metadata.party_name ? (
                              <Badge variant="outline" className="text-[10px]">
                                party: {chunk.metadata.party_name}
                              </Badge>
                            ) : null}
                            {effectiveOverride?.type === "candidate" ? (
                              <Badge variant="outline" className="text-[10px]">
                                candidate: {effectiveOverride.name}
                              </Badge>
                            ) : chunk.metadata.candidate_name ? (
                              <Badge variant="outline" className="text-[10px]">
                                candidate: {chunk.metadata.candidate_name}
                              </Badge>
                            ) : null}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Job row — for processing and completed tables
// ---------------------------------------------------------------------------

function JobRow({
  job,
  onRetry,
}: {
  job: JobStatus;
  onRetry?: () => void;
}) {
  const progress =
    job.status === "error" ? 0 : (job.progress ?? stageProgress(job.status));
  const isDone = job.status === "done";
  const isError = job.status === "error";

  return (
    <tr className="border-border border-b last:border-b-0">
      <td className="px-4 py-3 font-medium">
        <div className="flex items-center gap-2">
          <FileText className="text-muted-foreground size-4 shrink-0" />
          <span className="max-w-[180px] truncate" title={job.filename}>
            {job.filename}
          </span>
        </div>
      </td>

      <td className="text-muted-foreground px-4 py-3">
        {job.assigned_to ? (
          <span
            title={`${job.assigned_to.target_type}: ${job.assigned_to.target_id} (${Math.round(job.assigned_to.confidence * 100)}%)`}
          >
            {job.assigned_to.target_name}
          </span>
        ) : (
          <span className="text-muted-foreground/50 italic">detecting...</span>
        )}
      </td>

      <td className="px-4 py-3">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1.5 text-xs">
            {isDone && <CheckCircle2 className="size-3.5 text-green-500" />}
            {isError && <XCircle className="text-destructive size-3.5" />}
            {!isDone && !isError && (
              <Loader2 className="text-primary size-3.5 animate-spin" />
            )}
            <span
              className={
                isDone
                  ? "text-green-600"
                  : isError
                    ? "text-destructive"
                    : "text-foreground"
              }
            >
              {isError ? (job.error ?? "Error") : stageLabel(job.status)}
            </span>
          </div>

          {!isDone && !isError && (
            <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
              <div
                className="bg-primary h-full rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
          {isDone && (
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-green-100 dark:bg-green-900/30">
              <div className="h-full w-full rounded-full bg-green-500" />
            </div>
          )}
        </div>
      </td>

      <td className="text-muted-foreground px-4 py-3 text-right tabular-nums">
        {job.chunks_indexed != null ? job.chunks_indexed : "-"}
      </td>

      {onRetry && (
        <td className="px-4 py-3">
          {isError && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onRetry}
              className="h-7 px-2"
            >
              <RefreshCw className="size-3.5" />
            </Button>
          )}
        </td>
      )}
    </tr>
  );
}
