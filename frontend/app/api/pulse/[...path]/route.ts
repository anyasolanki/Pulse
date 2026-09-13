const known = (suffix: string) => /^(health|v1\/(radar|profile|stories|stories\/\d+\/(history|explanation|wikipedia|predictions)|predictions(\/resolve)?))$/.test(suffix);

async function forward(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const suffix = path.join('/');
  if (!known(suffix))
    return Response.json({ detail: 'Unknown endpoint' }, { status: 404 });
  try {
    const url = new URL(request.url);
    const user = request.headers.get('X-Pulse-Local-User');
    const upstream = await fetch(`http://127.0.0.1:8000/${suffix}${url.search}`, {
      method: request.method, body: request.method === 'GET' ? undefined : await request.text(),
      signal: AbortSignal.timeout(20000), headers: { Accept: 'application/json', ...(user ? { 'X-Pulse-Local-User': user } : {}), ...(request.method === 'GET' ? {} : { 'Content-Type': 'application/json' }) },
    });
    return new Response(await upstream.text(), { status: upstream.status,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
  } catch {
    return Response.json({ detail: 'Pulse cannot reach the local data service. Check that Docker and the API are running.' }, { status: 503 });
  }
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) { return forward(request, context); }
export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) { return forward(request, context); }
