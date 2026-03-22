import { NextResponse } from 'next/server';
import { Langfuse } from 'langfuse';

const langfuse = process.env.LANGFUSE_SECRET_KEY ? new Langfuse() : null;

export async function POST(req: Request) {
  if (!langfuse) {
    return NextResponse.json({ ok: false, reason: 'langfuse-not-configured' }, { status: 503 });
  }

  const body = await req.json();
  const { traceId, value, comment } = body as {
    traceId: string;
    value: 'like' | 'dislike';
    comment?: string;
  };

  if (!traceId || !value) {
    return NextResponse.json({ ok: false, reason: 'missing-fields' }, { status: 400 });
  }

  langfuse.score({
    traceId,
    name: 'user-feedback',
    value: value === 'like' ? 1 : 0,
    comment,
  });

  await langfuse.flushAsync();

  return NextResponse.json({ ok: true });
}
