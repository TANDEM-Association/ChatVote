"use client";

import React, { useCallback, useState } from "react";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  type Candidate,
  type Municipality,
} from "@lib/election/election.types";
import { getCandidatesByMunicipality } from "@lib/election/election-firebase-server";
import { getParties } from "@lib/firebase/firebase-server";
import { useIsMounted } from "@lib/hooks/use-is-mounted";
import { type PartyDetails } from "@lib/party-details";
import { cn } from "@lib/utils";
import { track } from "@vercel/analytics/react";
import {
  ArrowLeftIcon,
  GlobeIcon,
  Loader2Icon,
  MapPinIcon,
  MessageCircleIcon,
  UserPen,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { BorderTrail } from "../ui/border-trail";
import { Button } from "../ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Skeleton } from "../ui/skeleton";

import MunicipalitySearch from "./municipality-search";

// Button with animated border trail on hover
type ChatButtonProps = {
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
};

const ChatButton = ({ onClick, children, className }: ChatButtonProps) => {
  return (
    <Button
      onClick={onClick}
      className={cn(
        "group relative overflow-hidden rounded-full border border-neutral-950 transition-all duration-300 ease-in-out hover:border-transparent dark:border-neutral-100",
        className,
      )}
      size="lg"
    >
      <BorderTrail
        className="opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        size={60}
        contentRadius={24}
        transition={{
          repeat: Number.POSITIVE_INFINITY,
          duration: 2,
          ease: "linear",
        }}
        style={{
          boxShadow:
            "0px 0px 60px 30px rgb(147 51 234), 0 0 100px 60px rgb(59 130 246), 0 0 140px 90px rgb(236 72 153)",
        }}
      />
      {children}
    </Button>
  );
};

type Props = {
  className?: string;
};

type Scope = "local" | "national";
type FlowStep = "scope" | "municipality" | "parties";

const MAX_PARTIES_DISPLAY = 6;

const HomeElectionFlow = ({ className }: Props) => {
  const t = useTranslations("electionFlow");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const isMounted = useIsMounted();

  // Flow state
  const [scope, setScope] = useState<Scope | null>(null);
  const [currentStep, setCurrentStep] = useState<FlowStep>("scope");
  const [selectedMunicipality, setSelectedMunicipality] =
    useState<Municipality | null>(null);

  // Data state
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState(false);
  const [parties, setParties] = useState<PartyDetails[]>([]);
  const [isLoadingParties, setIsLoadingParties] = useState(false);

  // Handle scope selection
  const handleScopeChange = useCallback(async (value: Scope) => {
    setScope(value);

    if (value === "national") {
      // National scope - load parties and stay on scope step
      setCurrentStep("scope");
      setIsLoadingParties(true);
      try {
        const partiesData = await getParties();
        setParties(partiesData.slice(0, MAX_PARTIES_DISPLAY));
      } catch (_) {
        toast.error(t("errorLoadingParties"));
        setParties([]);
      } finally {
        setIsLoadingParties(false);
      }
    } else {
      // Local scope - go to municipality search
      setCurrentStep("municipality");
    }

    // Reset state
    setSelectedMunicipality(null);
    setCandidates([]);
  }, []);

  // Handle municipality selection
  const handleSelectMunicipality = useCallback(
    async (municipality: Municipality) => {
      setSelectedMunicipality(municipality);
      setCurrentStep("parties");

      // Load candidates for this municipality
      setIsLoadingCandidates(true);

      try {
        const candidatesData = await getCandidatesByMunicipality(
          municipality.code,
        );
        setCandidates(candidatesData);
      } catch (error) {
        console.error("Error loading candidates:", error);
        toast.error(t("errorLoadingCandidates"));
        setCandidates([]);
      } finally {
        setIsLoadingCandidates(false);
      }
    },
    [],
  );

  // Handle municipality clear
  const handleClearMunicipality = useCallback(() => {
    setSelectedMunicipality(null);
    setCandidates([]);
    setCurrentStep("municipality");
  }, []);

  // Handle back navigation
  const handleBack = useCallback(() => {
    if (currentStep === "parties") {
      setCurrentStep("municipality");
      setSelectedMunicipality(null);
      setCandidates([]);
    } else if (currentStep === "municipality") {
      setCurrentStep("scope");
      setScope(null);
    }
  }, [currentStep]);

  // Navigate to chat
  const handleStartChat = useCallback(
    (municipalityCode?: string) => {
      track("election_flow_chat_started", {
        scope: scope ?? "unknown",
        municipality_code: municipalityCode ?? null,
      });

      if (municipalityCode !== undefined) {
        router.push(`/chat?municipality_code=${municipalityCode}`);
      } else {
        router.push("/chat");
      }
    },
    [router, scope],
  );

  // Get step number for progress indicator (always out of 3)
  const getStepNumber = (): number => {
    if (currentStep === "scope") {
      // National shows step 2 when selected, local stays at step 1 until next
      return scope === "national" ? 2 : 1;
    }

    if (currentStep === "municipality") {
      return 2;
    }

    if (currentStep === "parties") {
      return 3;
    }

    return 1;
  };

  const stepNumber = getStepNumber();

  // Render skeleton during SSR and hydration to avoid Radix UI Select hydration mismatch
  if (isMounted === false) {
    return (
      <div className={cn("w-full space-y-6", className)}>
        <div className="flex h-10 items-center justify-between">
          <div />
          <Skeleton className="h-5 w-24" />
        </div>
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Skeleton className="size-5" />
            <Skeleton className="h-6 w-64" />
          </div>
          <Skeleton className="h-10 w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className={cn("w-full space-y-6", className)}>
      {/* Progress indicator */}
      <div className="flex h-10 items-center justify-between">
        <div className="flex items-center gap-2">
          {currentStep === "municipality" || currentStep === "parties" ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleBack}
              className="mr-2 pl-0!"
            >
              <ArrowLeftIcon className="mr-1 size-4" />
              {tCommon("back")}
            </Button>
          ) : null}
        </div>
        <div className="text-muted-foreground text-sm">
          {tCommon("step", { current: stepNumber, total: 3 })}
        </div>
      </div>

      {/* Step 1: Scope selection */}
      {currentStep === "scope" ? (
        <div className="space-y-4">
          <div className="flex items-center gap-2 max-md:justify-center">
            <GlobeIcon className="size-5" />
            <h2 className="text-sm font-semibold">{t("dialogueWith")}</h2>
          </div>

          <Select
            value={scope ?? undefined}
            onValueChange={(value) => handleScopeChange(value as Scope)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t("selectScope")} />
            </SelectTrigger>
            <SelectContent className="border-border overflow-hidden rounded-md border bg-neutral-200 shadow-lg data-[side=bottom]:translate-y-px dark:bg-purple-900">
              <SelectItem
                value="local"
                className="cursor-pointer rounded-md px-3 py-2 transition-all duration-300 ease-in-out hover:bg-neutral-700"
              >
                <div className="flex items-center gap-2">
                  <MapPinIcon className="size-4" />
                  <span>{t("local")}</span>
                </div>
              </SelectItem>
              <SelectItem
                value="national"
                className="cursor-pointer rounded-md px-3 py-2 transition-all duration-300 ease-in-out hover:bg-neutral-700"
              >
                <div className="flex items-center gap-2">
                  <GlobeIcon className="size-4" />
                  <span>{t("national")}</span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>

          {/* National scope: show parties and chat button */}
          {scope === "national" ? (
            <div className="flex flex-col space-y-6 pt-4">
              {isLoadingParties ? (
                <div className="flex flex-col items-center justify-center py-8">
                  <Loader2Icon className="text-primary size-8 animate-spin" />
                  <p className="text-muted-foreground mt-3 text-sm">
                    {t("loadingParties")}
                  </p>
                </div>
              ) : parties.length > 0 ? (
                <div className="flex flex-row items-center justify-center gap-2">
                  {parties.map((party) => (
                    <div
                      key={party.party_id}
                      className="flex flex-col items-center gap-2"
                    >
                      <div className="rounded-md bg-white p-2 shadow-lg">
                        <Image
                          src={party.logo_url}
                          alt={party.name}
                          width={0}
                          height={0}
                          sizes="100vw"
                          className="size-16 rounded-full object-contain"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}

              <p className="text-muted-foreground text-sm">
                {t("askQuestions")}
              </p>
              <ChatButton onClick={() => handleStartChat()}>
                <MessageCircleIcon className="mr-2 size-5" />
                {t("chatWithAI")}
              </ChatButton>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Step 2: Municipality search (local scope only) */}
      {currentStep === "municipality" ? (
        <MunicipalitySearch
          selectedMunicipality={selectedMunicipality}
          onSelectMunicipality={handleSelectMunicipality}
        />
      ) : null}

      {/* Step 3: Candidates list (local scope only) */}
      {currentStep === "parties" ? (
        isLoadingCandidates ? (
          <div className="flex flex-col items-center justify-center py-12">
            <Loader2Icon className="text-primary size-8 animate-spin" />
            <p className="text-muted-foreground mt-3 text-sm">
              {t("loadingCandidates")}
            </p>
          </div>
        ) : selectedMunicipality !== null ? (
          <div className="flex flex-col space-y-4">
            <div className="flex items-center gap-2">
              <MapPinIcon className="size-5" />
              <h2 className="text-lg font-semibold">
                {t("candidatesIn", { municipality: selectedMunicipality.nom })}
              </h2>
            </div>

            {candidates.length > 0 ? (
              <React.Fragment>
                {/* Candidates list */}
                <div className="flex flex-col gap-3">
                  {candidates.map((candidate) => (
                    <div
                      key={candidate.candidate_id}
                      className="flex cursor-pointer items-center gap-4 overflow-hidden rounded-lg border border-neutral-700 p-4 transition-colors hover:bg-neutral-900"
                    >
                      <div className="shrink-0 rounded-full">
                        {candidate.photo_url !== null &&
                        candidate.photo_url !== "" ? (
                          <Image
                            src={candidate.photo_url}
                            alt={`${candidate.first_name} ${candidate.last_name}`}
                            width={72}
                            height={72}
                            className="size-10 rounded-full object-cover"
                          />
                        ) : (
                          <UserPen className="size-10" strokeWidth={1} />
                        )}
                      </div>
                      <div className="flex min-w-0 flex-1 flex-row gap-8">
                        <div className="flex shrink-0 flex-col gap-1 whitespace-nowrap">
                          <div className="flex items-baseline gap-2 text-sm">
                            <span className="text-neutral-400">
                              {t("firstName")}
                            </span>
                            <span className="font-medium">
                              {candidate.first_name}
                            </span>
                          </div>
                          <div className="flex items-baseline gap-2 text-sm">
                            <span className="text-neutral-400">
                              {t("lastName")}
                            </span>
                            <span className="font-medium">
                              {candidate.last_name}
                            </span>
                          </div>
                        </div>
                        <div className="flex min-w-0 flex-col gap-1 text-sm">
                          <div className="flex items-baseline gap-2">
                            <span className="shrink-0 text-neutral-400">
                              {candidate.party_ids.length > 1
                                ? t("parties")
                                : t("party")}
                            </span>
                            <span className="truncate font-medium">
                              {candidate.party_ids
                                .map((party) => party.toUpperCase())
                                .join(", ")}
                            </span>
                          </div>
                          {candidate.website_url !== null && (
                            <div className="flex min-w-0 items-baseline gap-2">
                              <span className="shrink-0 text-neutral-400">
                                {t("website")}
                              </span>
                              <Link
                                href={candidate.website_url}
                                target="_blank"
                                className="truncate font-medium underline hover:text-neutral-300"
                              >
                                {candidate.website_url}
                              </Link>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <ChatButton
                  onClick={() => handleStartChat(selectedMunicipality.code)}
                  className="w-fit self-center"
                >
                  <MessageCircleIcon className="mr-2 size-5" />
                  {t("chatWithAIAbout", {
                    municipality: selectedMunicipality.nom,
                  })}
                </ChatButton>
              </React.Fragment>
            ) : (
              <div className="py-8 text-center">
                <p className="text-muted-foreground">{t("noCandidates")}</p>
                <Button
                  onClick={() => handleStartChat(selectedMunicipality.code)}
                  className="mt-4"
                  variant="outline"
                >
                  <MessageCircleIcon className="mr-2 size-4" />
                  {t("chatAnyway")}
                </Button>
              </div>
            )}
          </div>
        ) : null
      ) : null}
    </div>
  );
};

export default HomeElectionFlow;
