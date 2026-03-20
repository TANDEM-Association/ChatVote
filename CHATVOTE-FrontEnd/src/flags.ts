import { flag } from '@vercel/flags/next';

export const enableAiSdk = flag<boolean>({
  key: 'enable-ai-sdk',
  description: 'Enable AI SDK chat mode',
  defaultValue: false,
  decide() {
    return process.env.NEXT_PUBLIC_ENABLE_AI_SDK === 'true';
  },
});

export const enableCommuneDashboard = flag<boolean>({
  key: 'enable-commune-dashboard',
  description: 'Enable commune dashboard mini widget',
  defaultValue: false,
  decide() {
    return process.env.NEXT_PUBLIC_ENABLE_COMMUNE_DASHBOARD === 'true';
  },
});
