"use client";

import { type Source } from "@lib/stores/chat-store.types";
import { buildPdfUrl } from "@lib/utils";

const testSources: Source[] = [
  // 1. Manifesto PDF (S3 URL with .pdf)
  {
    source: "Les Écologistes - Programme électoral",
    url: "https://chatvote-public-assets.s3.fr-par.scw.cloud/public/europe-ecologie-les-verts/programme.pdf",
    page: 25,
    content_preview: "Transition écologique...",
    source_document: "election_manifesto",
    document_publish_date: "",
  },

  // 2. Profession de foi (S3 URL with .pdf) - AFTER backfill
  {
    source: "Eric CIOTTI - Profession de foi",
    url: "https://chatvote-public-assets.s3.fr-par.scw.cloud/public/professions_de_foi/06088/cand-06088-7.pdf",
    page: 1,
    content_preview: "Notre programme pour Nice...",
    source_document: "profession_de_foi",
    document_publish_date: "",
  },

  // 3. Profession de foi with NULL url (broken case)
  {
    source: "Eric CIOTTI - Profession de foi",
    url: "",
    page: 1,
    content_preview: "Notre programme pour Nice...",
    source_document: "profession_de_foi",
    document_publish_date: "",
  },

  // 4. Candidate website (HTML page)
  {
    source: "Sébastien DELOGU - Html",
    url: "https://sebastiendelogu2026.fr/programme/chapitre-2",
    page: 0,
    content_preview: "Programme pour Marseille...",
    source_document: "candidate_website_programme",
    document_publish_date: "",
  },

  // 5. Candidate website PDF transcription
  {
    source: "Emmanuel GRÉGOIRE - Pdf_transcription",
    url: "https://emmanuel-gregoire-2026.fr",
    page: 1,
    content_preview: "Projet pour Paris...",
    source_document: "candidate_website_pdf_transcription",
    document_publish_date: "",
  },

  // 6. External PDF (CORS issue scenario)
  {
    source: "Programme Bianchi",
    url: "https://bianchi2026.fr/wp-content/uploads/2026/01/Programme2026_OlivierBianchi.pdf",
    page: 1,
    content_preview: "Programme pour Clermont...",
    source_document: "election_manifesto",
    document_publish_date: "",
  },

  // 7. Government PDF (profession de foi from ministry)
  {
    source: "Profession de foi officielle",
    url: "https://programme-candidats.interieur.gouv.fr/elections-municipales-2026/data/pdf/1-06088-7.pdf",
    page: 1,
    content_preview: "Document officiel...",
    source_document: "profession_de_foi",
    document_publish_date: "",
  },
];

function getSourceDescription(index: number): string {
  const descriptions = [
    "Manifesto PDF — S3 URL with .pdf → should open PDF viewer",
    "Profession de foi — S3 URL with .pdf (post-backfill) → should open PDF viewer",
    "Profession de foi — NULL url (broken case) → should do nothing",
    "Candidate website HTML page — no .pdf in URL → should open URL directly",
    "Candidate website PDF transcription — no .pdf in URL → should open URL directly",
    "External PDF (CORS risk) — .pdf in URL but 3rd-party host → should open PDF viewer",
    "Government PDF — .pdf in URL, official ministry host → should open PDF viewer",
  ];
  return descriptions[index] ?? "";
}

function computeStatus(source: Source): {
  hasUrl: boolean;
  isPdf: boolean;
  pdfUrl: string | null;
} {
  const hasUrl = Boolean(source.url && source.url.startsWith("http"));

  const isPdf =
    hasUrl &&
    (source.url.includes(".pdf") ||
      source.source?.toLowerCase().endsWith(".pdf") ||
      source.source_document?.toLowerCase().endsWith(".pdf"));

  let pdfUrl: string | null = null;
  if (isPdf) {
    try {
      const built = buildPdfUrl(source);
      pdfUrl = built ? built.toString() : null;
    } catch {
      pdfUrl = null;
    }
  }

  return { hasUrl, isPdf, pdfUrl };
}

function onReferenceClick(source: Source) {
  const url = source.url;
  if (!url || !url.startsWith("http")) return;

  const isPdf =
    url.includes(".pdf") ||
    source.source?.toLowerCase().endsWith(".pdf") ||
    source.source_document?.toLowerCase().endsWith(".pdf");

  if (isPdf) {
    const pdfUrl = buildPdfUrl(source);
    if (pdfUrl) {
      window.open(pdfUrl.toString(), "_blank");
      return;
    }
  }

  window.open(url, "_blank");
}

function StatusPill({
  active,
  label,
}: {
  active: boolean;
  label: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        active
          ? "bg-green-100 text-green-800"
          : "bg-red-100 text-red-700"
      }`}
    >
      {active ? "✓" : "✗"} {label}
    </span>
  );
}

export default function SourceLinksDevPage() {
  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">
            Source Link Debug Page
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Tests how different source types resolve to clickable links via{" "}
            <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-xs">
              buildPdfUrl
            </code>{" "}
            and the{" "}
            <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-xs">
              onReferenceClick
            </code>{" "}
            logic from{" "}
            <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-xs">
              chat-markdown.tsx
            </code>
            .
          </p>
        </div>

        <div className="grid gap-6">
          {testSources.map((source, index) => {
            const { hasUrl, isPdf, pdfUrl } = computeStatus(source);

            return (
              <div
                key={index}
                className="rounded-xl border border-gray-200 bg-white shadow-sm"
              >
                {/* Card header */}
                <div className="flex items-center gap-3 border-b border-gray-100 px-5 py-4">
                  <button
                    onClick={() => onReferenceClick(source)}
                    title={`${source.source} - Page: ${source.page}`}
                    className="flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white shadow transition hover:bg-blue-700 active:scale-95"
                  >
                    {index + 1}
                  </button>
                  <div>
                    <p className="font-semibold text-gray-900">
                      {source.source}
                    </p>
                    <p className="text-xs text-gray-400">
                      {getSourceDescription(index)}
                    </p>
                  </div>
                </div>

                {/* Card body */}
                <div className="space-y-3 px-5 py-4">
                  {/* Status indicators */}
                  <div className="flex flex-wrap gap-2">
                    <StatusPill active={hasUrl} label="Has URL" />
                    <StatusPill active={isPdf} label="Is PDF" />
                    <StatusPill
                      active={isPdf && pdfUrl !== null}
                      label="PDF viewer URL built"
                    />
                  </div>

                  {/* Metadata grid */}
                  <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
                    <dt className="font-medium text-gray-500">source_document</dt>
                    <dd className="font-mono text-gray-800">
                      {source.source_document || (
                        <span className="text-gray-400 italic">empty</span>
                      )}
                    </dd>

                    <dt className="font-medium text-gray-500">page</dt>
                    <dd className="font-mono text-gray-800">{source.page}</dd>

                    <dt className="font-medium text-gray-500">url</dt>
                    <dd className="break-all font-mono text-xs text-gray-800">
                      {source.url || (
                        <span className="text-red-500 italic">empty string</span>
                      )}
                    </dd>

                    <dt className="font-medium text-gray-500">content_preview</dt>
                    <dd className="text-gray-700 italic">
                      &ldquo;{source.content_preview}&rdquo;
                    </dd>
                  </dl>

                  {/* Resolved PDF viewer URL */}
                  <div className="rounded-lg bg-gray-50 px-4 py-3">
                    <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400">
                      Resolved viewer URL (buildPdfUrl output)
                    </p>
                    {pdfUrl ? (
                      <p className="break-all font-mono text-xs text-indigo-700">
                        {pdfUrl}
                      </p>
                    ) : (
                      <p className="font-mono text-xs text-gray-400 italic">
                        {isPdf ? "buildPdfUrl returned null" : "N/A — not a PDF"}
                      </p>
                    )}
                  </div>

                  {/* Action buttons */}
                  <div className="flex flex-wrap gap-2 pt-1">
                    <button
                      onClick={() => onReferenceClick(source)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={!hasUrl}
                    >
                      <span>▶</span>
                      Simulate reference click
                    </button>

                    {isPdf && pdfUrl && (
                      <a
                        href={pdfUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50"
                      >
                        <span>📄</span>
                        Open in PDF Viewer
                      </a>
                    )}

                    {hasUrl && !isPdf && (
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50"
                      >
                        <span>🔗</span>
                        Open URL directly
                      </a>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <p className="mt-8 text-center text-xs text-gray-400">
          Dev page — not shown in production navigation
        </p>
      </div>
    </div>
  );
}
