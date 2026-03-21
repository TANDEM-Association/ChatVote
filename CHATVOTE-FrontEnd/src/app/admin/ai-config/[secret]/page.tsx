"use client";

import { useEffect, useState } from "react";

import Link from "next/link";
import { useParams } from "next/navigation";

interface AiConfig {
  maxSearchCalls: number;
  docsPerCandidateShallow: number;
  docsPerCandidateDeep: number;
  docsPerSearchShallow: number;
  docsPerSearchDeep: number;
  scoreThreshold: number;
  primaryModel: string;
  fallbackModel: string;
  rateLimitMax: number;
  enableRag: boolean;
  enablePerplexity: boolean;
  enableDataGouv: boolean;
  enableWidgets: boolean;
  enableVotingRecords: boolean;
  enableParliamentary: boolean;
}

const MODEL_OPTIONS = [
  { value: "scaleway-qwen", label: "Scaleway Qwen" },
  { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
  { value: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
];

const DEFAULTS: AiConfig = {
  maxSearchCalls: 3,
  docsPerCandidateShallow: 3,
  docsPerCandidateDeep: 5,
  docsPerSearchShallow: 6,
  docsPerSearchDeep: 8,
  scoreThreshold: 0.25,
  primaryModel: "scaleway-qwen",
  fallbackModel: "gemini-2.5-flash",
  rateLimitMax: 20,
  enableRag: true,
  enablePerplexity: true,
  enableDataGouv: false,
  enableWidgets: false,
  enableVotingRecords: false,
  enableParliamentary: false,
};

const FEATURE_TOGGLES: Array<{ key: keyof AiConfig; label: string; description: string }> = [
  { key: "enableRag", label: "RAG Search", description: "Recherche dans les programmes et sites des candidats" },
  { key: "enablePerplexity", label: "Web Search (Perplexity)", description: "Recherche web pour l'actualité et les événements récents" },
  { key: "enableDataGouv", label: "data.gouv.fr", description: "Données ouvertes gouvernementales" },
  { key: "enableWidgets", label: "Widgets", description: "Visualisations et graphiques interactifs" },
  { key: "enableVotingRecords", label: "Votes parlementaires", description: "Historique des votes de l'Assemblée nationale" },
  { key: "enableParliamentary", label: "Questions parlementaires", description: "Questions posées au gouvernement" },
];

export default function AiConfigPage() {
  const { secret } = useParams<{ secret: string }>();

  const [form, setForm] = useState<AiConfig>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  useEffect(() => {
    async function fetchConfig() {
      try {
        const res = await fetch("/api/admin/ai-config");
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
  }, []);

  function setField<K extends keyof AiConfig>(key: K, value: AiConfig[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setMessage(null);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch("/api/admin/ai-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        setMessage({ type: "success", text: "Configuration saved. Changes take effect within 60 seconds." });
      } else {
        const text = await res.text();
        setMessage({ type: "error", text: `Save failed (${res.status}): ${text}` });
      }
    } catch (err) {
      setMessage({ type: "error", text: `Network error: ${err instanceof Error ? err.message : "Unknown"}` });
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setForm(DEFAULTS);
    setMessage(null);
  }

  return (
    <>
      <meta name="robots" content="noindex, nofollow" />
      <div className="bg-background text-foreground flex min-h-screen flex-col">
        <div className="mx-auto w-full max-w-2xl space-y-6 px-4 py-10">
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
              <Section title="Search Parameters">
                <Field label="Max search calls" hint="Distinct topic searches per request (1-10)">
                  <NumberInput value={form.maxSearchCalls} min={1} max={10} onChange={(v) => setField("maxSearchCalls", v)} />
                </Field>
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Docs/candidate — shallow" hint="1-20">
                    <NumberInput value={form.docsPerCandidateShallow} min={1} max={20} onChange={(v) => setField("docsPerCandidateShallow", v)} />
                  </Field>
                  <Field label="Docs/candidate — deep" hint="1-20">
                    <NumberInput value={form.docsPerCandidateDeep} min={1} max={20} onChange={(v) => setField("docsPerCandidateDeep", v)} />
                  </Field>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Docs/search — shallow" hint="1-30">
                    <NumberInput value={form.docsPerSearchShallow} min={1} max={30} onChange={(v) => setField("docsPerSearchShallow", v)} />
                  </Field>
                  <Field label="Docs/search — deep" hint="1-30">
                    <NumberInput value={form.docsPerSearchDeep} min={1} max={30} onChange={(v) => setField("docsPerSearchDeep", v)} />
                  </Field>
                </div>
                <Field label="Score threshold" hint="Minimum similarity (0-1)">
                  <NumberInput value={form.scoreThreshold} min={0} max={1} step={0.05} onChange={(v) => setField("scoreThreshold", v)} />
                </Field>
              </Section>

              {/* Model Selection */}
              <Section title="Model Selection">
                <Field label="Primary model" hint="Used for all requests">
                  <ModelSelect value={form.primaryModel} onChange={(v) => setField("primaryModel", v)} />
                </Field>
                <Field label="Fallback model" hint="Used when primary fails">
                  <ModelSelect value={form.fallbackModel} onChange={(v) => setField("fallbackModel", v)} />
                </Field>
              </Section>

              {/* Features */}
              <Section title="Features (Tools)">
                {FEATURE_TOGGLES.map((ft) => (
                  <div key={ft.key} className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{ft.label}</p>
                      <p className="text-muted-foreground text-xs">{ft.description}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setField(ft.key, !(form[ft.key] as boolean))}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                        form[ft.key] ? "bg-primary" : "bg-muted"
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block size-5 rounded-full bg-white shadow ring-0 transition-transform ${
                          form[ft.key] ? "translate-x-5" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </div>
                ))}
              </Section>

              {/* Rate Limiting */}
              <Section title="Rate Limiting">
                <Field label="Max requests per minute" hint="Per user (1-100)">
                  <NumberInput value={form.rateLimitMax} min={1} max={100} onChange={(v) => setField("rateLimitMax", v)} />
                </Field>
              </Section>

              {message && (
                <div className={`rounded-lg border px-4 py-3 text-sm ${
                  message.type === "success"
                    ? "border-green-500/30 bg-green-500/10 text-green-400"
                    : "border-destructive/30 bg-destructive/5 text-destructive"
                }`}>
                  {message.text}
                </div>
              )}

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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-border rounded-xl border">
      <div className="border-border border-b px-5 py-3">
        <h2 className="text-sm font-semibold tracking-wide uppercase">{title}</h2>
      </div>
      <div className="space-y-4 p-5">{children}</div>
    </section>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{label}</label>
      {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
      {children}
    </div>
  );
}

function NumberInput({ value, min, max, step = 1, onChange }: { value: number; min: number; max: number; step?: number; onChange: (v: number) => void }) {
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

function ModelSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="border-border bg-background text-foreground focus:ring-ring w-full rounded-lg border px-3 py-2 text-sm focus:ring-1 focus:outline-none"
    >
      {MODEL_OPTIONS.map((opt) => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  );
}
