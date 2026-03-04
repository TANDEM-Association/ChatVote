import { type LLMSize } from "@lib/socket.types";

export type ChatSession = {
  id: string;
  user_id: string;
  party_id?: string;
  is_public?: boolean;
  title?: string;
  created_at?: Date;
  updated_at?: Date;
  party_ids?: string[];
  tenant_id?: string;
};

export type ProposedQuestion = {
  id: string;
  content: string;
  topic: string;
  location: "banner" | "chat" | "home";
  partyId: string;
};

export type SourceDocument = {
  id: string;
  storage_url: string;
  name: string;
  publish_date?: Date;
  party_id: string;
};

export const DEFAULT_LLM_SIZE: LLMSize = "large";

export type Tenant = {
  id: string;
  name: string;
  llm_size?: LLMSize;
};

export type LlmSystemStatus = {
  is_at_rate_limit: boolean;
};
