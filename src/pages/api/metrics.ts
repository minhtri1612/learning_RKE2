import type { NextApiRequest, NextApiResponse } from 'next'

const body = [
  '# HELP meo_backend_up Set to 1 while this process is running (canary analysis instant query).',
  '# TYPE meo_backend_up gauge',
  'meo_backend_up{service="backend"} 1',
  '',
].join('\n')

export default function handler(_req: NextApiRequest, res: NextApiResponse) {
  res.setHeader('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
  res.status(200).send(body)
}
