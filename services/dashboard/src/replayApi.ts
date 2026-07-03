import { apiFetch } from './apiClient'
import type { ReplayRunDetail, ReplayRunsResponse } from './types'

async function parseJson<T>(response: Response, label: string): Promise<T> {
  if (!response.ok) throw new Error(`${label} HTTP ${response.status}`)
  return await response.json() as T
}

export async function listReplayRuns(limit = 20): Promise<ReplayRunsResponse> {
  const response = await apiFetch(`/api/replay/runs?limit=${encodeURIComponent(String(limit))}`)
  return parseJson<ReplayRunsResponse>(response, 'replay runs')
}

export async function getReplayRun(runId: string, maxRows = 500): Promise<ReplayRunDetail> {
  const response = await apiFetch(
    `/api/replay/runs/${encodeURIComponent(runId)}?max_rows=${encodeURIComponent(String(maxRows))}`
  )
  return parseJson<ReplayRunDetail>(response, 'replay detail')
}
