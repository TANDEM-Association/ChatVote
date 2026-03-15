'use client';

import { useEffect, useState } from 'react';
import { type ElectoralList } from '@lib/election/election.types';
import { type PartyDetails } from '@lib/party-details';
import { cn, toTitleCase } from '@lib/utils';
import { Check, ExternalLink, FileText } from 'lucide-react';
import Image from 'next/image';

type CandidateListItem = ElectoralList & {
  candidate_id: string | null;
  party_ids: string[];
  website_url: string | null;
  manifesto_pdf_url: string | null;
};

type CandidateListsResponse = {
  lists: CandidateListItem[];
  source: 'electoral_lists' | 'candidates';
};

type Props = {
  municipalityCode: string;
  /** When true, items are clickable and toggle selection */
  selectable?: boolean;
  /** Currently selected candidate_ids (controlled from parent) */
  selectedIds?: Set<string>;
  /** Called when a candidate is toggled — passes the full updated partyIds array */
  onSelectionChange?: (partyIds: string[]) => void;
};

export default function AiSdkCandidateBar({
  municipalityCode,
  selectable = false,
  selectedIds,
  onSelectionChange,
}: Props) {
  const [candidates, setCandidates] = useState<CandidateListItem[]>([]);
  const [parties, setParties] = useState<PartyDetails[]>([]);
  const [loading, setLoading] = useState(true);
  // Internal selection state when parent doesn't provide controlled selectedIds
  const [internalSelected, setInternalSelected] = useState<Set<string>>(new Set());

  const selected = selectedIds ?? internalSelected;

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      setLoading(true);

      // Try candidate lists (electoral lists enriched with URLs)
      try {
        const res = await fetch(
          `/api/candidate-lists?municipalityCode=${encodeURIComponent(municipalityCode)}`,
        );
        if (res.ok) {
          const data: CandidateListsResponse = await res.json();
          if (!cancelled && data.lists.length > 0) {
            setCandidates(data.lists);
            setParties([]);
            setLoading(false);

            // Reset selection when municipality changes — user picks candidates
            if (selectable && !selectedIds) {
              setInternalSelected(new Set());
              onSelectionChange?.([]);
            }
            return;
          }
        }
      } catch {
        // fall through to parties
      }

      // Fallback to parties only if no candidate data
      try {
        const res = await fetch(
          `/api/candidates?municipalityCode=${encodeURIComponent(municipalityCode)}`,
        );
        if (res.ok) {
          const data: PartyDetails[] = await res.json();
          if (!cancelled) setParties(data);
        }
      } catch {
        // silently ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [municipalityCode]);

  function handleToggle(list: CandidateListItem) {
    if (!selectable || !list.candidate_id) return;

    const next = new Set(selected);
    if (next.has(list.candidate_id)) {
      next.delete(list.candidate_id);
    } else {
      next.add(list.candidate_id);
    }

    if (!selectedIds) {
      setInternalSelected(next);
    }

    // Derive partyIds from currently selected candidates
    const selectedPartyIds = [
      ...new Set(
        candidates
          .filter((c) => c.candidate_id && next.has(c.candidate_id))
          .flatMap((c) => c.party_ids),
      ),
    ];
    onSelectionChange?.(selectedPartyIds);
  }

  if (loading || (candidates.length === 0 && parties.length === 0)) return null;

  return (
    <div className="bg-muted/40 px-3 py-2 md:px-9">
      <div className="mx-auto flex max-w-3xl items-center gap-2 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <span className="text-muted-foreground shrink-0 text-xs font-medium">
          {selectable ? 'Sélectionnez\u00a0:' : 'Listes\u00a0:'}
        </span>
        {candidates.length > 0
          ? candidates.map((list) => {
              const isSelected =
                selectable && list.candidate_id ? selected.has(list.candidate_id) : false;

              return (
                <button
                  key={list.candidate_id || list.panel_number || list.head_last_name}
                  type="button"
                  onClick={() => handleToggle(list)}
                  disabled={!selectable}
                  className={cn(
                    'flex shrink-0 flex-col items-start gap-0.5 rounded-lg border px-2.5 py-1.5 text-left transition-all',
                    selectable && 'cursor-pointer hover:shadow-sm',
                    !selectable && 'cursor-default',
                    isSelected
                      ? 'border-primary bg-primary/5 ring-primary/30 ring-1'
                      : 'border-white/10 bg-white/5',
                  )}
                >
                  <div className="flex items-center gap-1.5 text-xs font-medium">
                    {selectable && (
                      <span
                        className={cn(
                          'flex size-4 shrink-0 items-center justify-center rounded-full border transition-colors',
                          isSelected
                            ? 'border-primary bg-primary text-primary-foreground'
                            : 'border-muted-foreground/30',
                        )}
                      >
                        {isSelected && <Check className="size-2.5" />}
                      </span>
                    )}
                    <span className="text-foreground font-semibold">{list.head_last_name}</span>
                    <span className="text-muted-foreground/70 max-w-[120px] truncate">
                      {toTitleCase(list.list_short_label || list.list_label)}
                    </span>
                  </div>
                  {(list.website_url || list.manifesto_pdf_url) && (
                    <div className="flex items-center gap-2">
                      {list.website_url && (
                        <a
                          href={list.website_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-primary/70 hover:text-primary flex items-center gap-0.5 text-[10px]"
                        >
                          <ExternalLink className="size-2.5" />
                          Site
                        </a>
                      )}
                      {list.manifesto_pdf_url && (
                        <a
                          href={list.manifesto_pdf_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-primary/70 hover:text-primary flex items-center gap-0.5 text-[10px]"
                        >
                          <FileText className="size-2.5" />
                          Programme
                        </a>
                      )}
                    </div>
                  )}
                </button>
              );
            })
          : parties.map((party) => (
              <div
                key={party.party_id}
                className="border-border text-muted-foreground flex shrink-0 items-center gap-1.5 rounded-full border bg-background px-2.5 py-1 text-xs font-medium"
              >
                {party.logo_url && (
                  <Image
                    src={party.logo_url}
                    alt=""
                    width={16}
                    height={16}
                    className="size-4 rounded-full object-cover"
                    unoptimized
                  />
                )}
                {party.name}
              </div>
            ))}
      </div>
    </div>
  );
}
