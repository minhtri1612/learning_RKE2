import { NextResponse } from 'next/server'

// Prometheus text exposition for PodMonitor scrape (/metrics). Next.js has no default /metrics.
const body = [
  '# HELP meo_backend_up Set to 1 while this process is running (canary analysis instant query).',
  '# TYPE meo_backend_up gauge',
  'meo_backend_up{service="backend"} 1',
  '',
].join('\n')

export async function GET() {
  return new NextResponse(body, {
    status: 200,
    headers: {
      'Content-Type': 'text/plain; version=0.0.4; charset=utf-8',
    },
  })
}
