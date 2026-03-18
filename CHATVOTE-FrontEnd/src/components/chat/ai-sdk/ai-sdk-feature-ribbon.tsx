"use client";

import { useAiSdkFeaturesStore } from "@lib/stores/ai-sdk-features-store";
import { cn } from "@lib/utils";
import {
  BarChart3,
  Database,
  Globe,
  type LucideIcon,
  MessageSquare,
  Search,
  Vote,
} from "lucide-react";

const ICON_MAP: Record<string, LucideIcon> = {
  Search,
  Database,
  Globe,
  BarChart3,
  Vote,
  MessageSquare,
};

export default function AiSdkFeatureRibbon() {
  const features = useAiSdkFeaturesStore((s) => s.features);
  const toggleFeature = useAiSdkFeaturesStore((s) => s.toggleFeature);

  return (
    <div className="mt-2 px-1">
      <div className="mx-auto flex max-w-3xl justify-center gap-1.5 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {features.map((feature) => {
          const Icon = ICON_MAP[feature.icon] ?? Search;
          return (
            <button
              key={feature.id}
              onClick={() => toggleFeature(feature.id)}
              title={feature.description}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                feature.enabled
                  ? "border-primary/40 bg-primary/15 text-primary"
                  : "text-muted-foreground hover:text-foreground border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10",
              )}
            >
              <Icon className="size-3.5" />
              {feature.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
