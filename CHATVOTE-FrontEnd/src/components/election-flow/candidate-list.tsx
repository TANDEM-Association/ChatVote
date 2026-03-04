"use client";

import React from "react";

import { useRouter } from "next/navigation";

import {
  type Candidate,
  type Municipality,
} from "@lib/election/election.types";
import { type PartyDetails } from "@lib/party-details";
import { cn } from "@lib/utils";
import { track } from "@vercel/analytics/react";
import { MessageCircleIcon, UsersIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "../ui/button";

import CandidateCard from "./candidate-card";

type Props = {
  candidates: Candidate[];
  parties: PartyDetails[];
  municipality: Municipality;
  selectedCandidates: Candidate[];
  onSelectCandidate: (candidate: Candidate) => void;
  className?: string;
};

const MAX_SELECTABLE_CANDIDATES = 7;

const CandidateList = ({
  candidates,
  parties,
  municipality,
  selectedCandidates,
  onSelectCandidate,
  className,
}: Props) => {
  const t = useTranslations("electionFlow");
  const tCommon = useTranslations("common");
  const router = useRouter();

  const handleStartChat = () => {
    if (selectedCandidates.length === 0) {
      return;
    }

    // Get unique party IDs from all selected candidates
    const partyIds = [
      ...new Set(selectedCandidates.flatMap((c) => c.party_ids)),
    ];

    // Track the event
    track("election_flow_chat_started", {
      municipality: municipality.nom,
      municipality_code: municipality.code,
      candidates_count: selectedCandidates.length,
      parties_count: partyIds.length,
    });

    // Navigate to chat with selected party IDs
    const partyParams = partyIds.map((id) => `party_id=${id}`).join("&");
    router.push(`/chat?${partyParams}`);
  };

  if (candidates.length === 0) {
    return (
      <div className={cn("py-8 text-center", className)}>
        <UsersIcon className="text-muted-foreground mx-auto mb-3 size-12" />
        <h3 className="font-medium">{t("noCandidatesFound")}</h3>
        <p className="text-muted-foreground mt-1 text-sm">
          {t("noCandidatesYet", { municipality: municipality.nom })}
        </p>
      </div>
    );
  }

  return (
    <div className={cn("w-full space-y-4", className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <UsersIcon className="size-5" />
          <h2 className="text-lg font-semibold">
            {t("candidatesIn", { municipality: municipality.nom })}
          </h2>
        </div>
        <span className="text-muted-foreground text-sm">
          {candidates.length}{" "}
          {candidates.length > 1 ? t("candidates") : t("candidate")}
        </span>
      </div>

      <p className="text-muted-foreground text-sm">
        {t("selectCandidatesDescription")}
      </p>

      {/* Candidates grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {candidates.map((candidate) => {
          const isSelected = selectedCandidates.some(
            (c) => c.candidate_id === candidate.candidate_id,
          );

          return (
            <CandidateCard
              key={candidate.candidate_id}
              candidate={candidate}
              parties={parties}
              isSelected={isSelected}
              onSelect={onSelectCandidate}
            />
          );
        })}
      </div>

      {/* Selection summary and action */}
      {selectedCandidates.length > 0 ? (
        <div className="bg-muted/50 sticky bottom-4 flex items-center justify-between gap-4 rounded-lg border p-4 shadow-lg backdrop-blur">
          <div className="flex-1">
            <p className="font-medium">
              {selectedCandidates.length > 1
                ? t("selectedCountPlural", { count: selectedCandidates.length })
                : t("selectedCount", { count: selectedCandidates.length })}
            </p>
            <p className="text-muted-foreground text-xs">
              {selectedCandidates.length < MAX_SELECTABLE_CANDIDATES
                ? t("canSelectMore", {
                    count:
                      MAX_SELECTABLE_CANDIDATES - selectedCandidates.length,
                  })
                : tCommon("maxReached")}
            </p>
          </div>
          <Button onClick={handleStartChat} className="shrink-0">
            <MessageCircleIcon className="mr-2 size-4" />
            {t("chatWithAI")}
          </Button>
        </div>
      ) : null}
    </div>
  );
};

export default CandidateList;
