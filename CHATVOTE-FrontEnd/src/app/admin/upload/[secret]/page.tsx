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

import { useParams } from "next/navigation";

import { Badge } from "@components/ui/badge";
import { Button } from "@components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@components/ui/card";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@components/ui/select";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  FileText,
  Loader2,
  RefreshCw,
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

interface ChunkPreview {
  index: number;
  content: string;
  length: number;
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

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_SOCKET_URL ||
  "http://localhost:8080";

const ACCEPTED_TYPES = [
  "application/pdf",
  "text/plain",
];
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
// Page component
// ---------------------------------------------------------------------------

export default function AdminUploadPage() {
  const { secret } = useParams<{ secret: string }>();

  const [jobs, setJobs] = useState<Map<string, JobStatus>>(new Map());
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [targets, setTargets] = useState<Target[]>([]);
  const [targetsLoading, setTargetsLoading] = useState(true);

  // Per-job manual override selection (job_id -> "type:id")
  const [manualOverrides, setManualOverrides] = useState<
    Map<string, string>
  >(new Map());

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dragCounterRef = useRef(0);

  // ---- Load available targets on mount ----

  useEffect(() => {
    async function loadTargets() {
      try {
        const resp = await fetch(`${API_URL}/api/v1/admin/upload-targets`, {
          headers: { "X-Upload-Secret": secret },
        });
        if (resp.ok) {
          const data = await resp.json();
          setTargets(data.targets || []);
        }
      } catch {
        // Non-critical — manual selection won't be available
      } finally {
        setTargetsLoading(false);
      }
    }
    loadTargets();
  }, [secret]);

  // ---- Polling for job status updates ----

  const activeJobIds = useRef<Set<string>>(new Set());

  const pollStatuses = useCallback(async () => {
    if (activeJobIds.current.size === 0) return;

    try {
      const resp = await fetch(`${API_URL}/api/v1/admin/upload-status`, {
        headers: { "X-Upload-Secret": secret },
      });

      if (resp.status === 404 || resp.status === 403) {
        setNotFound(true);
        return;
      }
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
          if (
            status.status === "done" ||
            status.status === "error" ||
            status.status === "preview"
          ) {
            activeJobIds.current.delete(id);
          }
        }
        return next;
      });
    } catch {
      // Silently ignore poll errors
    }
  }, [secret]);

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

  // ---- Upload handler (preview mode) ----

  const handleUpload = useCallback(
    async (files: File[]) => {
      const valid = files.filter(isValidFile);
      if (valid.length === 0) {
        setUploadError(
          "No valid files selected. Only PDF and TXT are accepted.",
        );
        return;
      }

      setUploadError(null);
      setIsUploading(true);

      try {
        const formData = new FormData();
        valid.forEach((f) => formData.append("files", f));
        formData.append("mode", "preview");

        const resp = await fetch(`${API_URL}/api/v1/admin/upload`, {
          method: "POST",
          headers: { "X-Upload-Secret": secret },
          body: formData,
        });

        if (resp.status === 404 || resp.status === 403) {
          setNotFound(true);
          return;
        }

        if (!resp.ok) {
          const text = await resp.text();
          setUploadError(`Upload failed (${resp.status}): ${text}`);
          return;
        }

        const data = (await resp.json()) as {
          jobs: Array<{
            job_id: string;
            filename: string;
            status: JobStage;
            preview?: PreviewData;
          }>;
        };

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
            });
            // Poll if not yet in preview/done/error
            if (!["preview", "done", "error"].includes(job.status)) {
              activeJobIds.current.add(job.job_id);
            }
          }
          return next;
        });
      } catch (err) {
        setUploadError(
          `Network error: ${err instanceof Error ? err.message : "Unknown error"}`,
        );
      } finally {
        setIsUploading(false);
      }
    },
    [secret, isValidFile],
  );

  // ---- Confirm handler ----

  const handleConfirm = useCallback(
    async (jobId: string) => {
      const override = manualOverrides.get(jobId);
      let body: Record<string, string> = {};
      if (override && override !== "auto") {
        const [targetType, targetId] = override.split(":", 2);
        body = { target_type: targetType, target_id: targetId };
      }

      // Optimistically update status
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
          `${API_URL}/api/v1/admin/upload-confirm/${jobId}`,
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
    [secret, manualOverrides],
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
    (j) =>
      !["preview", "done", "error"].includes(j.status),
  );
  const completedJobs = jobList.filter(
    (j) => j.status === "done" || j.status === "error",
  );

  // ---- Grouped targets ----

  const partyTargets = useMemo(
    () => targets.filter((t) => t.type === "party"),
    [targets],
  );
  const candidateTargets = useMemo(
    () => targets.filter((t) => t.type === "candidate"),
    [targets],
  );

  // ---- Not-found gate ----

  if (notFound) {
    return (
      <div className="bg-background flex h-screen items-center justify-center">
        <p className="text-muted-foreground text-lg">Page not found.</p>
      </div>
    );
  }

  // ---- Render ----

  return (
    <>
      <meta name="robots" content="noindex, nofollow" />

      <div className="bg-background text-foreground flex min-h-screen flex-col">
        <div className="mx-auto w-full max-w-4xl space-y-6 px-4 py-10">
          {/* Header */}
          <div>
            <h1 className="text-2xl font-bold">Document Upload</h1>
            <p className="text-muted-foreground mt-1 text-sm">
              Drop PDF or TXT files to preview, configure source assignment,
              then index into Qdrant.
            </p>
          </div>

          {/* Drop zone */}
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
            } `}
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
              Uploading and analyzing files...
            </div>
          )}

          {/* Preview section */}
          {previewJobs.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">
                  Review &amp; Configure ({previewJobs.length} file
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
                  selectedOverride={manualOverrides.get(job.job_id) || "auto"}
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
      </div>
    </>
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

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <FileText className="text-muted-foreground size-5 shrink-0" />
            <div className="min-w-0">
              <CardTitle className="text-base truncate">
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

          <div className="flex items-center gap-1.5 shrink-0">
            <Button
              variant="ghost"
              size="sm"
              onClick={onRemove}
              className="h-7 px-2 text-muted-foreground hover:text-destructive"
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
            <label className="text-sm font-medium">
              Assign to
            </label>
            <Select value={selectedOverride} onValueChange={onOverrideChange}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Auto-detect" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">
                  {autoAssignment
                    ? `Auto: ${autoAssignment.target_name}`
                    : "Auto-detect (failed)"}
                </SelectItem>
                <SelectSeparator />

                {partyTargets.length > 0 && (
                  <SelectGroup>
                    <SelectLabel>Parties</SelectLabel>
                    {partyTargets.map((t) => (
                      <SelectItem key={t.id} value={`party:${t.id}`}>
                        {t.name}
                        {t.abbreviation ? ` (${t.abbreviation})` : ""}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                )}

                {candidateTargets.length > 0 && (
                  <>
                    <SelectSeparator />
                    <SelectGroup>
                      <SelectLabel>Candidates</SelectLabel>
                      {candidateTargets.map((t) => (
                        <SelectItem key={t.id} value={`candidate:${t.id}`}>
                          {t.name}
                          {t.municipality ? ` — ${t.municipality}` : ""}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </>
                )}

                {targetsLoading && (
                  <SelectItem value="_loading" disabled>
                    Loading targets...
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>

          <Button
            onClick={onConfirm}
            size="sm"
            className="h-9 gap-1.5"
            disabled={
              !autoAssignment && selectedOverride === "auto"
            }
          >
            <Send className="size-3.5" />
            Index
          </Button>
        </div>

        {/* Expandable preview */}
        {preview && preview.chunk_previews && preview.chunk_previews.length > 0 && (
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
                  <p className="text-xs leading-relaxed whitespace-pre-wrap">
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
                      <p className="text-xs leading-relaxed">
                        {chunk.content}
                        {chunk.content.length < chunk.length ? "..." : ""}
                      </p>
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
      {/* Filename */}
      <td className="px-4 py-3 font-medium">
        <div className="flex items-center gap-2">
          <FileText className="text-muted-foreground size-4 shrink-0" />
          <span className="max-w-[180px] truncate" title={job.filename}>
            {job.filename}
          </span>
        </div>
      </td>

      {/* Assigned to */}
      <td className="text-muted-foreground px-4 py-3">
        {job.assigned_to ? (
          <span
            title={`${job.assigned_to.target_type}: ${job.assigned_to.target_id} (${Math.round(job.assigned_to.confidence * 100)}%)`}
          >
            {job.assigned_to.target_name}
          </span>
        ) : (
          <span className="text-muted-foreground/50 italic">
            detecting...
          </span>
        )}
      </td>

      {/* Status + progress bar */}
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

          {/* Progress bar */}
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

      {/* Chunks indexed */}
      <td className="text-muted-foreground px-4 py-3 text-right tabular-nums">
        {job.chunks_indexed != null ? job.chunks_indexed : "-"}
      </td>

      {/* Retry */}
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
