"use client";

import { useParams } from "next/navigation";
import {
  useState,
  useCallback,
  useRef,
  useEffect,
  type DragEvent,
  type ChangeEvent,
} from "react";

import { UploadCloud, FileText, RefreshCw, CheckCircle2, XCircle, Loader2 } from "lucide-react";

import { Button } from "@components/ui/button";

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
  | "done"
  | "error";

interface JobStatus {
  job_id: string;
  filename: string;
  status: JobStage;
  progress: number;
  assigned_to?: { target_name: string; target_id: string; target_type: string; confidence: number } | null;
  collection?: string;
  chunks_indexed?: number;
  error?: string;
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

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dragCounterRef = useRef(0);

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
            next.set(id, { ...status, job_id: id });
          }
          if (status.status === "done" || status.status === "error") {
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

  // ---- Upload handler ----

  const handleUpload = useCallback(
    async (files: File[]) => {
      const valid = files.filter(isValidFile);
      if (valid.length === 0) {
        setUploadError("No valid files selected. Only PDF and TXT are accepted.");
        return;
      }

      setUploadError(null);
      setIsUploading(true);

      try {
        const formData = new FormData();
        valid.forEach((f) => formData.append("files", f));

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
          jobs: Array<{ job_id: string; filename: string; status: JobStage }>;
        };

        setJobs((prev) => {
          const next = new Map(prev);
          for (const job of data.jobs) {
            next.set(job.job_id, {
              job_id: job.job_id,
              filename: job.filename,
              status: job.status,
              progress: stageProgress(job.status),
            });
            activeJobIds.current.add(job.job_id);
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

  // ---- Retry handler ----

  const handleRetry = useCallback(
    (jobId: string) => {
      const job = jobs.get(jobId);
      if (!job) return;

      // Re-upload requires the original file, which we don't keep.
      // Instead remove the failed job so the user can re-drop the file.
      setJobs((prev) => {
        const next = new Map(prev);
        next.delete(jobId);
        return next;
      });
      activeJobIds.current.delete(jobId);
    },
    [jobs],
  );

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
      // Reset input so re-selecting same file triggers change
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [handleUpload],
  );

  // ---- Not-found gate ----

  if (notFound) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground text-lg">Page not found.</p>
      </div>
    );
  }

  // ---- Render ----

  const jobList = Array.from(jobs.values());

  return (
    <>
      {/* noindex */}
      <meta name="robots" content="noindex, nofollow" />

      <div className="flex min-h-screen flex-col bg-background text-foreground">
        <div className="mx-auto w-full max-w-3xl px-4 py-10 space-y-8">
          {/* Header */}
          <div>
            <h1 className="text-2xl font-bold">Document Upload</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Admin &mdash; drag &amp; drop PDF or TXT files to index into the
              RAG vector store.
            </p>
          </div>

          {/* Drop zone */}
          <div
            onDragEnter={onDragEnter}
            onDragLeave={onDragLeave}
            onDragOver={onDragOver}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`
              flex cursor-pointer flex-col items-center justify-center gap-3
              rounded-xl border-2 border-dashed p-12 transition-colors
              ${
                isDragging
                  ? "border-primary bg-primary/5"
                  : "border-border-subtle hover:border-primary/50 hover:bg-surface/50"
              }
            `}
          >
            <UploadCloud
              className={`size-10 ${isDragging ? "text-primary" : "text-muted-foreground"}`}
            />
            <p className="text-sm text-muted-foreground text-center">
              {isDragging ? (
                <span className="font-semibold text-primary">Drop files here</span>
              ) : (
                <>
                  Drop files here or{" "}
                  <span className="font-semibold text-primary underline underline-offset-2">
                    click to browse
                  </span>
                </>
              )}
            </p>
            <p className="text-xs text-muted-foreground/70">PDF, TXT</p>
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
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {uploadError}
            </div>
          )}

          {/* Uploading spinner */}
          {isUploading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Uploading files...
            </div>
          )}

          {/* Upload queue / status table */}
          {jobList.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold">Upload Queue</h2>

              <div className="overflow-hidden rounded-xl border border-border-subtle">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border-subtle bg-surface text-left text-xs uppercase text-muted-foreground tracking-wider">
                      <th className="px-4 py-2.5">File</th>
                      <th className="px-4 py-2.5">Assigned To</th>
                      <th className="px-4 py-2.5">Status</th>
                      <th className="px-4 py-2.5 text-right">Chunks</th>
                      <th className="px-4 py-2.5 w-10" />
                    </tr>
                  </thead>
                  <tbody>
                    {jobList.map((job) => (
                      <JobRow
                        key={job.job_id}
                        job={job}
                        onRetry={() => handleRetry(job.job_id)}
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
// Job row sub-component
// ---------------------------------------------------------------------------

function JobRow({ job, onRetry }: { job: JobStatus; onRetry: () => void }) {
  const progress = job.status === "error" ? 0 : (job.progress ?? stageProgress(job.status));
  const isDone = job.status === "done";
  const isError = job.status === "error";

  return (
    <tr className="border-b border-border-subtle last:border-b-0">
      {/* Filename */}
      <td className="px-4 py-3 font-medium">
        <div className="flex items-center gap-2">
          <FileText className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate max-w-[180px]" title={job.filename}>
            {job.filename}
          </span>
        </div>
      </td>

      {/* Assigned to */}
      <td className="px-4 py-3 text-muted-foreground">
        {job.assigned_to ? (
          <span title={`${job.assigned_to.target_type}: ${job.assigned_to.target_id} (${Math.round(job.assigned_to.confidence * 100)}%)`}>
            {job.assigned_to.target_name}
          </span>
        ) : (
          <span className="italic text-muted-foreground/50">detecting...</span>
        )}
      </td>

      {/* Status + progress bar */}
      <td className="px-4 py-3">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1.5 text-xs">
            {isDone && <CheckCircle2 className="size-3.5 text-green-500" />}
            {isError && <XCircle className="size-3.5 text-destructive" />}
            {!isDone && !isError && (
              <Loader2 className="size-3.5 animate-spin text-primary" />
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
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-border-subtle">
              <div
                className="h-full rounded-full bg-primary transition-all duration-500"
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
      <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
        {job.chunks_indexed != null ? job.chunks_indexed : "-"}
      </td>

      {/* Retry */}
      <td className="px-4 py-3">
        {isError && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onRetry}
            className="h-7 px-2"
            tooltip="Remove and re-upload"
          >
            <RefreshCw className="size-3.5" />
          </Button>
        )}
      </td>
    </tr>
  );
}
