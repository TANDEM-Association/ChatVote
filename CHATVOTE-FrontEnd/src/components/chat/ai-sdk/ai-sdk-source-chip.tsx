'use client';

import { ExternalLink } from 'lucide-react';

type Props = {
  source: {
    id?: string;
    url?: string;
    title?: string;
  };
};

export default function AiSdkSourceChip({ source }: Props) {
  if (!source.url && !source.title) return null;

  return (
    <a
      href={source.url || '#'}
      target="_blank"
      rel="noopener noreferrer"
      className="bg-primary/10 text-primary hover:bg-primary/20 my-1 mr-1 inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors"
    >
      <ExternalLink className="size-3" />
      {source.title || source.id || 'Source'}
    </a>
  );
}
