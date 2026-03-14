"use client";

import { useState } from "react";

import { cn } from "@lib/utils";

import { useChatStore } from "../providers/chat-store-provider";
import {
  trackDemographicAnswered,
  trackDemographicSkipped,
} from "@lib/firebase/analytics";
import type { UserDemographics } from "@lib/firebase/user-profile";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DemographicField = keyof Omit<UserDemographics, "updated_at">;

type DemographicQuestion = {
  field: DemographicField;
  label: string;
  options: Array<{ value: string; label: string }>;
  multiSelect?: boolean;
};

// ---------------------------------------------------------------------------
// Questions config
// ---------------------------------------------------------------------------

const DEMOGRAPHIC_QUESTIONS: DemographicQuestion[] = [
  {
    field: "gender",
    label: "Pour mieux répondre à vos préoccupations, vous êtes…",
    options: [
      { value: "female", label: "Femme" },
      { value: "male", label: "Homme" },
      { value: "other", label: "Autre" },
    ],
  },
  {
    field: "age_range",
    label: "Pour mieux comprendre votre situation, quelle est votre tranche d'âge ?",
    options: [
      { value: "18-25", label: "18-25" },
      { value: "26-35", label: "26-35" },
      { value: "36-50", label: "36-50" },
      { value: "51-65", label: "51-65" },
      { value: "65+", label: "65+" },
    ],
  },
  {
    field: "occupation",
    label: "Quelle est votre situation professionnelle ?",
    options: [
      { value: "student", label: "Étudiant·e" },
      { value: "employee", label: "Salarié·e" },
      { value: "self_employed", label: "Indépendant·e" },
      { value: "retired", label: "Retraité·e" },
      { value: "job_seeker", label: "En recherche d'emploi" },
      { value: "other", label: "Autre" },
    ],
  },
  {
    field: "concern_topics",
    label: "Quels sujets vous préoccupent le plus ?",
    multiSelect: true,
    options: [
      { value: "sante", label: "Santé" },
      { value: "logement", label: "Logement" },
      { value: "education", label: "Éducation" },
      { value: "securite", label: "Sécurité" },
      { value: "economie", label: "Économie" },
      { value: "environnement", label: "Environnement" },
      { value: "transport", label: "Transport" },
    ],
  },
];

// Message count thresholds: after which user message each question appears
const TRIGGER_THRESHOLDS = [1, 3, 5, 7];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function getNextDemographicQuestion(
  messageCount: number,
  demographics: UserDemographics | null,
): DemographicQuestion | null {
  for (let i = 0; i < DEMOGRAPHIC_QUESTIONS.length; i++) {
    const threshold = TRIGGER_THRESHOLDS[i];
    if (messageCount < threshold) continue;

    const question = DEMOGRAPHIC_QUESTIONS[i];
    const currentValue = demographics?.[question.field];

    // Skip if already answered
    if (question.multiSelect) {
      if (Array.isArray(currentValue) && currentValue.length > 0) continue;
    } else {
      if (currentValue) continue;
    }

    return question;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type Props = {
  question: DemographicQuestion;
  messageNumber: number;
};

export default function DemographicBubble({ question, messageNumber }: Props) {
  const setUserDemographic = useChatStore((s) => s.setUserDemographic);
  const [answered, setAnswered] = useState(false);
  const [skipped, setSkipped] = useState(false);
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);

  if (answered) {
    return (
      <div className="flex justify-center py-1">
        <span className="text-xs text-muted-foreground">Merci !</span>
      </div>
    );
  }

  if (skipped) return null;

  const handleSelect = (value: string) => {
    if (question.multiSelect) {
      setSelectedTopics((prev) =>
        prev.includes(value)
          ? prev.filter((v) => v !== value)
          : [...prev, value],
      );
      return;
    }

    // Show "Merci !" feedback first, then persist to store after a short
    // delay.  Without this, the Zustand update triggers a parent re-render
    // that unmounts this component before "Merci !" is visible.
    setAnswered(true);
    trackDemographicAnswered({
      field: question.field,
      value,
      message_number: messageNumber,
    });
    setTimeout(() => {
      setUserDemographic(question.field, value);
    }, 1500);
  };

  const handleValidateTopics = () => {
    if (selectedTopics.length === 0) return;
    setAnswered(true);
    trackDemographicAnswered({
      field: question.field,
      value: selectedTopics.join(","),
      message_number: messageNumber,
    });
    setTimeout(() => {
      setUserDemographic(question.field, selectedTopics);
    }, 1500);
  };

  const handleSkip = () => {
    trackDemographicSkipped({
      field: question.field,
      message_number: messageNumber,
    });
    setSkipped(true);
  };

  return (
    <div className="flex justify-center py-2">
      <div className="max-w-md rounded-xl border border-primary/20 bg-primary/5 px-4 py-3">
        <p className="mb-3 text-center text-sm text-foreground">
          {question.label}
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          {question.options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => handleSelect(option.value)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs font-medium transition-all",
                question.multiSelect && selectedTopics.includes(option.value)
                  ? "border-primary bg-primary text-white"
                  : "border-primary/30 bg-transparent text-foreground hover:border-primary hover:bg-primary/10",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        {question.multiSelect && selectedTopics.length > 0 && (
          <div className="mt-3 flex justify-center">
            <button
              type="button"
              onClick={handleValidateTopics}
              className="rounded-full bg-primary px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-primary/80"
            >
              Valider
            </button>
          </div>
        )}
        <div className="mt-2 flex justify-center">
          <button
            type="button"
            onClick={handleSkip}
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            Passer
          </button>
        </div>
      </div>
    </div>
  );
}
