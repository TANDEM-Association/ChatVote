"use client";

import { useEffect, useState } from "react";

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
  enableRagflow: boolean;
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
  enableRagflow: false,
};

const FEATURE_TOGGLES: Array<{ key: keyof AiConfig; label: string; description: string }> = [
  { key: "enableRag", label: "RAG Search", description: "Recherche dans les programmes et sites des candidats" },
  { key: "enablePerplexity", label: "Web Search (Perplexity)", description: "Recherche web pour l'actualité" },
  { key: "enableDataGouv", label: "data.gouv.fr", description: "Données ouvertes gouvernementales" },
  { key: "enableWidgets", label: "Widgets", description: "Visualisations et graphiques interactifs" },
  { key: "enableRagflow", label: "RAGFlow", description: "Base de connaissances enrichie avec parsing avancé (OCR, tableaux)" },
];

export default function AiConfigTab() {
  const [form, setForm] = useState<AiConfig>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    fetch("/api/admin/ai-config")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => { if (data) setForm((prev) => ({ ...prev, ...data })); })
      .catch(() => {})
      .finally(() => setLoading(false));
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
        setMessage({ type: "error", text: `Save failed (${res.status})` });
      }
    } catch (err) {
      setMessage({ type: "error", text: `Error: ${err instanceof Error ? err.message : "Unknown"}` });
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="text-muted-foreground py-12 text-center text-sm">Loading configuration...</div>;

  return (
    <form onSubmit={handleSave} className="mx-auto max-w-2xl space-y-6 py-4">
      {/* Features */}
      <Section title="Features (Tools)">
        {FEATURE_TOGGLES.map((ft) => (
          <div key={ft.key} className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">{ft.label}</p>
              <p className="text-muted-foreground text-xs">{ft.description}</p>
            </div>
            <Toggle checked={form[ft.key] as boolean} onChange={() => setField(ft.key, !(form[ft.key] as boolean))} />
          </div>
        ))}
      </Section>

      {/* Search */}
      <Section title="Search Parameters">
        <Field label="Max search calls" hint="1-10">
          <NumInput value={form.maxSearchCalls} min={1} max={10} onChange={(v) => setField("maxSearchCalls", v)} />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Docs/candidate — shallow" hint="1-20">
            <NumInput value={form.docsPerCandidateShallow} min={1} max={20} onChange={(v) => setField("docsPerCandidateShallow", v)} />
          </Field>
          <Field label="Docs/candidate — deep" hint="1-20">
            <NumInput value={form.docsPerCandidateDeep} min={1} max={20} onChange={(v) => setField("docsPerCandidateDeep", v)} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Docs/search — shallow" hint="1-30">
            <NumInput value={form.docsPerSearchShallow} min={1} max={30} onChange={(v) => setField("docsPerSearchShallow", v)} />
          </Field>
          <Field label="Docs/search — deep" hint="1-30">
            <NumInput value={form.docsPerSearchDeep} min={1} max={30} onChange={(v) => setField("docsPerSearchDeep", v)} />
          </Field>
        </div>
        <Field label="Score threshold" hint="0-1">
          <NumInput value={form.scoreThreshold} min={0} max={1} step={0.05} onChange={(v) => setField("scoreThreshold", v)} />
        </Field>
      </Section>

      {/* Model */}
      <Section title="Model Selection">
        <Field label="Primary model">
          <select value={form.primaryModel} onChange={(e) => setField("primaryModel", e.target.value)} className="border-border bg-background text-foreground w-full rounded-lg border px-3 py-2 text-sm focus:outline-none">
            {MODEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Fallback model">
          <select value={form.fallbackModel} onChange={(e) => setField("fallbackModel", e.target.value)} className="border-border bg-background text-foreground w-full rounded-lg border px-3 py-2 text-sm focus:outline-none">
            {MODEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
      </Section>

      {/* Rate Limiting */}
      <Section title="Rate Limiting">
        <Field label="Max requests per minute" hint="1-100">
          <NumInput value={form.rateLimitMax} min={1} max={100} onChange={(v) => setField("rateLimitMax", v)} />
        </Field>
      </Section>

      {message && (
        <div className={`rounded-lg border px-4 py-3 text-sm ${message.type === "success" ? "border-green-500/30 bg-green-500/10 text-green-400" : "border-red-500/30 bg-red-500/10 text-red-400"}`}>
          {message.text}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button type="submit" disabled={saving} className="bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 rounded-lg px-5 py-2 text-sm font-medium">
          {saving ? "Saving..." : "Save configuration"}
        </button>
        <button type="button" onClick={() => { setForm(DEFAULTS); setMessage(null); }} className="border-border bg-card hover:bg-muted rounded-lg border px-5 py-2 text-sm font-medium">
          Reset to defaults
        </button>
      </div>
    </form>
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

function NumInput({ value, min, max, step = 1, onChange }: { value: number; min: number; max: number; step?: number; onChange: (v: number) => void }) {
  return (
    <input type="number" value={value} min={min} max={max} step={step} onChange={(e) => onChange(Number(e.target.value))}
      className="border-border bg-background text-foreground w-full rounded-lg border px-3 py-2 text-sm focus:outline-none" />
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button type="button" onClick={onChange}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${checked ? "bg-primary" : "bg-muted"}`}>
      <span className={`pointer-events-none inline-block size-5 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-5" : "translate-x-0"}`} />
    </button>
  );
}
