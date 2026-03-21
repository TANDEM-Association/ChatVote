import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type AiSdkFeature = {
  id: string;
  label: string;
  icon: string;
  description: string;
  enabled: boolean;
  toolNames: string[];
};

const DEFAULT_FEATURES: AiSdkFeature[] = [
  {
    id: 'rag',
    label: 'RAG Search',
    icon: 'Search',
    description: 'Recherche dans les programmes et sites des candidats',
    enabled: true,
    toolNames: ['searchPartyManifesto', 'searchCandidateWebsite'],
  },
  {
    id: 'data-gouv',
    label: 'data.gouv',
    icon: 'Database',
    description: 'Données ouvertes gouvernementales',
    enabled: false,
    toolNames: ['searchDataGouv'],
  },
  {
    id: 'perplexity',
    label: 'Web Search',
    icon: 'Globe',
    description: "Recherche web pour l'actualité",
    enabled: true,
    toolNames: ['webSearch'],
  },
  {
    id: 'widgets',
    label: 'Widgets',
    icon: 'BarChart3',
    description: 'Visualisations et graphiques interactifs',
    enabled: false,
    toolNames: ['renderWidget'],
  },
  {
    id: 'voting-records',
    label: 'Votes',
    icon: 'Vote',
    description: 'Historique des votes parlementaires',
    enabled: false,
    toolNames: ['searchVotingRecords'],
  },
  {
    id: 'parliamentary',
    label: 'Questions',
    icon: 'MessageSquare',
    description: 'Questions parlementaires',
    enabled: false,
    toolNames: ['searchParliamentaryQuestions'],
  },
];

type AiSdkFeaturesStore = {
  features: AiSdkFeature[];
  toggleFeature: (id: string) => void;
  getEnabledFeatureIds: () => string[];
};

export const useAiSdkFeaturesStore = create<AiSdkFeaturesStore>()(
  persist(
    (set, get) => ({
      features: DEFAULT_FEATURES,
      toggleFeature: (id: string) =>
        set((state) => ({
          features: state.features.map((f) =>
            f.id === id ? { ...f, enabled: !f.enabled } : f,
          ),
        })),
      getEnabledFeatureIds: () =>
        get().features.filter((f) => f.enabled).map((f) => f.id),
    }),
    { name: 'ai-sdk-features' },
  ),
);
