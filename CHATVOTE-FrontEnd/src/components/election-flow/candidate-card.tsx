"use client";

import React from "react";

import Image from "next/image";

import {
  type Candidate,
  isCoalitionCandidate,
} from "@lib/election/election.types";
import { type PartyDetails } from "@lib/party-details";
import { cn } from "@lib/utils";
import { CheckIcon, UserIcon, UsersIcon } from "lucide-react";

import { Badge } from "../ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../ui/card";

type Props = {
  candidate: Candidate;
  parties: PartyDetails[];
  isSelected?: boolean;
  onSelect?: (candidate: Candidate) => void;
};

const CandidateCard = ({ candidate, parties, isSelected, onSelect }: Props) => {
  const candidateParties = parties.filter((party) =>
    candidate.party_ids.includes(party.party_id),
  );
  const isCoalition = isCoalitionCandidate(candidate);

  return (
    <Card
      className={cn(
        "hover:border-primary/50 cursor-pointer transition-all hover:shadow-md",
        isSelected === true
          ? "border-primary bg-primary/5 ring-primary ring-2"
          : "",
      )}
      onClick={() => onSelect?.(candidate)}
    >
      <CardHeader className="p-4 pb-2">
        <div className="flex items-start gap-3">
          {/* Avatar / Photo */}
          <div className="bg-muted flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-full">
            {candidate.photo_url !== null ? (
              <Image
                src={candidate.photo_url}
                alt={`${candidate.first_name} ${candidate.last_name}`}
                width={48}
                height={48}
                className="size-full object-cover"
              />
            ) : (
              <UserIcon className="text-muted-foreground size-6" />
            )}
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <div>
                <CardTitle className="text-base">
                  {candidate.first_name} {candidate.last_name}
                </CardTitle>
                <CardDescription className="text-xs">
                  {candidate.position}
                </CardDescription>
              </div>

              {isSelected === true ? (
                <div className="bg-primary text-primary-foreground flex size-6 shrink-0 items-center justify-center rounded-full">
                  <CheckIcon className="size-4" />
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-4 pt-2">
        {/* Party logos */}
        <div className="mb-2 flex items-center gap-2">
          {candidateParties.map((party) => (
            <div
              key={party.party_id}
              className="flex size-8 items-center justify-center overflow-hidden rounded-md border bg-white"
              title={party.name}
            >
              <Image
                src={party.logo_url}
                alt={party.name}
                width={24}
                height={24}
                className="size-6 object-contain"
              />
            </div>
          ))}

          {isCoalition ? (
            <Badge variant="secondary" className="text-xs">
              <UsersIcon className="mr-1 size-3" />
              Coalition
            </Badge>
          ) : null}
        </div>

        {/* Bio excerpt */}
        <p className="text-muted-foreground line-clamp-2 text-xs">
          {candidate.bio}
        </p>

        {/* Incumbent badge */}
        {candidate.is_incumbent ? (
          <Badge variant="outline" className="mt-2 text-xs">
            Sortant
          </Badge>
        ) : null}
      </CardContent>
    </Card>
  );
};

export default CandidateCard;
