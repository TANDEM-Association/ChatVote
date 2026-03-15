import { QdrantClient } from '@qdrant/js-client-rest';

const qdrantUrl = process.env.QDRANT_URL || 'http://localhost:6333';
const qdrantApiKey = process.env.QDRANT_API_KEY;

export const qdrantClient = new QdrantClient({
  url: qdrantUrl,
  apiKey: qdrantApiKey,
  // For HTTPS endpoints (Scaleway), disable gRPC and use port 443
  ...(qdrantUrl.startsWith('https') ? { port: 443 } : {}),
});

// Collection names with env suffix
const env = process.env.ENV || 'dev';
export const COLLECTIONS = {
  allParties: `all_parties_${env}`,
  candidatesWebsites: `candidates_websites_${env}`,
  votingBehavior: `justified_voting_behavior_${env}`,
  parliamentaryQuestions: `parliamentary_questions_${env}`,
} as const;
