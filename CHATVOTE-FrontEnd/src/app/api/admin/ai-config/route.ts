import { type NextRequest, NextResponse } from 'next/server';
import { db } from '@lib/firebase/firebase-admin';
import { AI_CONFIG_DEFAULTS, type AiConfig } from '@lib/ai/ai-config';

export async function GET() {
  try {
    const doc = await db.collection('system_status').doc('ai_config').get();
    const data = doc.exists ? doc.data() : {};
    const config = { ...AI_CONFIG_DEFAULTS, ...data };
    return NextResponse.json(config);
  } catch (error) {
    console.error('[admin/ai-config] GET error:', error);
    return NextResponse.json(AI_CONFIG_DEFAULTS);
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json() as Partial<AiConfig>;

    // Validate numeric fields
    const validated: Record<string, unknown> = {};
    const numericFields = [
      'maxSearchCalls', 'docsPerCandidateShallow', 'docsPerCandidateDeep',
      'docsPerSearchShallow', 'docsPerSearchDeep', 'rateLimitMax',
    ] as const;

    for (const key of numericFields) {
      if (key in body) {
        const val = Number(body[key]);
        if (!isFinite(val) || val < 1) continue;
        validated[key] = val;
      }
    }

    if ('scoreThreshold' in body) {
      const val = Number(body.scoreThreshold);
      if (isFinite(val) && val >= 0 && val <= 1) {
        validated.scoreThreshold = val;
      }
    }

    const validModels = ['scaleway-qwen', 'gemini-2.5-flash', 'gemini-2.0-flash'];
    if ('primaryModel' in body && validModels.includes(body.primaryModel!)) {
      validated.primaryModel = body.primaryModel;
    }
    if ('fallbackModel' in body && validModels.includes(body.fallbackModel!)) {
      validated.fallbackModel = body.fallbackModel;
    }

    if ('enablePerplexity' in body) {
      validated.enablePerplexity = Boolean(body.enablePerplexity);
    }

    await db.collection('system_status').doc('ai_config').set(validated, { merge: true });

    const updated = await db.collection('system_status').doc('ai_config').get();
    const config = { ...AI_CONFIG_DEFAULTS, ...(updated.data() ?? {}) };

    return NextResponse.json(config);
  } catch (error) {
    console.error('[admin/ai-config] PUT error:', error);
    return NextResponse.json({ error: 'Failed to update config' }, { status: 500 });
  }
}
