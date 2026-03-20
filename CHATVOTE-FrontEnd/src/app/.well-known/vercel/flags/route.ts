import { verifyAccess, type ApiData } from '@vercel/flags';
import { NextResponse, type NextRequest } from 'next/server';
import * as flags from '../../../../flags';

export async function GET(request: NextRequest) {
  const access = await verifyAccess(request.headers.get('Authorization'));
  if (!access) return NextResponse.json(null, { status: 401 });

  const definitions: ApiData = Object.fromEntries(
    Object.values(flags).map((f) => [
      f.key,
      { description: f.description, origin: f.origin ?? 'https://app.chatvote.org' },
    ]),
  );

  return NextResponse.json<ApiData>(definitions);
}
