"use client";

import { useEffect, useState } from "react";

import Link from "next/link";
import { useParams } from "next/navigation";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AiConfig {
  max_search_calls: number;
  docs_per_candidate_shallow: number;
  docs_per_candidate_deep: number;
  docs_per_search_shallow: number;
  docs_per_search_deep: number;
  score_threshold: number;
  primary_model: string;
  fallback_model: string;
  rate_limit_max_per_minute: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_SOCKET_URL ||
  "http://localhost:8080";

const MODEL_OPTIONS = [
  { value: "scaleway-qwen", label: "Scaleway Qwen" },
  { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
  { value: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
];

const DEFAULTS: AiConfig = {
  max_search_calls: 3,
  docs_per_candidate_shallow: 5,
  docs_per_candidate_deep: 10,
  docs_per_search_shallow: 10,
  docs_per_search_deep: 20,
  score_threshold: 0.5,
  primary_model: "gemini-2.0-flash",
  fallback_model: "gemini-2.5-flash",
  rate_limit_max_per_minute: 10,
};

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function AiConfigPage() {
  const { secret } = useParams<{ secret: string }>();

  const [form, setForm] = useState<AiConfig>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  // Fetch current config on mount
  useEffect(() => {
    async function fetchConfig() {
      try {
        const res = await fetch("/api/admin/ai-config", {
          headers: { "X-Admin-Secret": secret },
        });
        if (res.ok) {
          const data = await res.json();
          setForm((prev) => ({ ...prev, ...data }));
        }
      } catch {
        // Non-critical — form keeps defaults
      } finally {
        setLoading(false);
      }
    }
    fetchConfig();
  }, [secret]);

  // Generic field setter
  function setField<K extends keyof AiConfig>(key: K, value: AiConfig[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setMessage(null);
  }

  // Save handler
  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch("/api/admin/ai-config", {
        method: "PUT",
        headers: {
          "X-Admin-Secret": secret,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        setMessage({ type: "success", text: "Configuration saved." });
      } else {
        const text = await res.text();
        setMessage({
          type: "error",
          text: `Save failed (${res.status}): ${text}`,
        });
      }
    } catch (err) {
      setMessage({
        type: "error",
        text: `Network error: ${err instanceof Error ? err.message : "Unknown error"}`,
      });
    } finally {
      setSaving(false);
    }
  }

  // Reset to defaults
  function handleReset() {
    setForm(DEFAULTS);
    setMessage(null);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <>
      <meta name="robots" content="noindex, nofollow" />

      <div className="bg-background text-foreground flex min-h-screen flex-col">
        <div className="mx-auto w-full max-w-2xl space-y-6 px-4 py-10">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">AI Configuration</h1>
              <p className="text-muted-foreground mt-1 text-sm">
                Adjust search, model, and rate limiting parameters.
              </p>
            </div>
            <Link
              href={`/admin/dashboard/${secret}`}
              className="text-muted-foreground hover:text-foreground text-sm underline underline-offset-2 transition-colors"
            >
              ← Back to dashboard
            </Link>
          </div>

          {loading ? (
            <div className="text-muted-foreground py-12 text-center text-sm">
              Loading configuration...
            </div>
          ) : (
            <form onSubmit={handleSave} className="space-y-6">
              {/* Search Parameters */}
              <section className="border-border rounded-xl border">
                <div className="border-border border-b px-5 py-3">
                  <h2 className="text-sm font-semibold tracking-wide uppercase">
                    Search Parameters
                  </h2>
                </div>
                <div className="space-y-4 p-5">
                  <Field
                    label="Max search calls"
                    hint="Number of search iterations per query"
                  >
                    <NumberInput
                      value={form.max_search_calls}
                      min={1}
                      max={10}
                      onChange={(v) => setField("max_search_calls", v)}
                    />
                  </Field>

                  <div className="grid grid-cols-2 gap-4">
                    <Field
                      label="Docs per candidate — shallow"
                      hint="min 1, max 20"
                    >
                      <NumberInput
                        value={form.docs_per_candidate_shallow}
                        min={1}
                        max={20}
                        onChange={(v) =>
                          setField("docs_per_candidate_shallow", v)
                        }
                      />
                    </Field>
                    <Field
                      label="Docs per candidate — deep"
                      hint="min 1, max 20"
                    >
                      <NumberInput
                        value={form.docs_per_candidate_deep}
                        min={1}
                        max={20}
                        onChange={(v) =>
                          setField("docs_per_candidate_deep", v)
                        }
                      />
                    </Field>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <Field
                      label="Docs per search — shallow"
                      hint="min 1, max 30"
                    >
                      <NumberInput
                        value={form.docs_per_search_shallow}
                        min={1}
                        max={30}
                        onChange={(v) =>
                          setField("docs_per_search_shallow", v)
                        }
                      />
                    </Field>
                    <Field
                      label="Docs per search — deep"
                      hint="min 1, max 30"
                    >
                      <NumberInput
                        value={form.docs_per_search_deep}
                        min={1}
                        max={30}
                        onChange={(v) => setField("docs_per_search_deep", v)}
                      />
                    </Field>
                  </div>

                  <Field
                    label="Score threshold"
                    hint="Minimum similarity score (0 – 1)"
                  >
                    <NumberInput
                      value={form.score_threshold}
                      min={0}
                      max={1}
                      step={0.05}
                      onChange={(v) => setField("score_threshold", v)}
                    />
                  </Field>
                </div>
              </section>

              {/* Model Selection */}
              <section className="border-border rounded-xl border">
                <div className="border-border border-b px-5 py-3">
                  <h2 className="text-sm font-semibold tracking-wide uppercase">
                    Model Selection
                  </h2>
                </div>
                <div className="space-y-4 p-5">
                  <Field label="Primary model" hint="Used for all requests">
                    <ModelSelect
                      value={form.primary_model}
                      onChange={(v) => setField("primary_model", v)}
                    />
                  </Field>
                  <Field
                    label="Fallback model"
                    hint="Used when primary model fails"
                  >
                    <ModelSelect
                      value={form.fallback_model}
                      onChange={(v) => setField("fallback_model", v)}
                    />
                  </Field>
                </div>
              </section>

              {/* Rate Limiting */}
              <section className="border-border rounded-xl border">
                <div className="border-border border-b px-5 py-3">
                  <h2 className="text-sm font-semibold tracking-wide uppercase">
                    Rate Limiting
                  </h2>
                </div>
                <div className="p-5">
                  <Field
                    label="Rate limit max per minute"
                    hint="Maximum requests per user per minute (1 – 100)"
                  >
                    <NumberInput
                      value={form.rate_limit_max_per_minute}
                      min={1}
                      max={100}
                      onChange={(v) => setField("rate_limit_max_per_minute", v)}
                    />
                  </Field>
                </div>
              </section>

              {/* Status message */}
              {message && (
                <div
                  className={`rounded-lg border px-4 py-3 text-sm ${
                    message.type === "success"
                      ? "border-green-500/30 bg-green-500/10 text-green-400"
                      : "border-destructive/30 bg-destructive/5 text-destructive"
                  }`}
                >
                  {message.text}
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center gap-3">
                <button
                  type="submit"
                  disabled={saving}
                  className="bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 rounded-lg px-5 py-2 text-sm font-medium transition-colors"
                >
                  {saving ? "Saving..." : "Save configuration"}
                </button>
                <button
                  type="button"
                  onClick={handleReset}
                  className="border-border bg-card text-foreground hover:bg-muted rounded-lg border px-5 py-2 text-sm font-medium transition-colors"
                >
                  Reset to defaults
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{label}</label>
      {hint && (
        <p className="text-muted-foreground text-xs">{hint}</p>
      )}
      {children}
    </div>
  );
}

function NumberInput({
  value,
  min,
  max,
  step = 1,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => onChange(Number(e.target.value))}
      className="border-border bg-background text-foreground focus:ring-ring w-full rounded-lg border px-3 py-2 text-sm focus:ring-1 focus:outline-none"
    />
  );
}

function ModelSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="border-border bg-background text-foreground focus:ring-ring w-full rounded-lg border px-3 py-2 text-sm focus:ring-1 focus:outline-none"
    >
      {MODEL_OPTIONS.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
