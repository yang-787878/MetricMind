import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, uploadDataset } from '@/lib/api'
import type { DatasetDetail, RunDetail } from '@/types/contract'

export const TERMINAL_STATUSES = new Set(['succeeded', 'partial', 'failed', 'cancelled'])

export function useDatasets(limit = 20) {
  return useQuery({
    queryKey: ['datasets', limit],
    queryFn: () => api.listDatasets(limit),
    staleTime: 15_000,
  })
}

export function useUploadDataset() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      file,
      onPhase,
    }: {
      file: File
      onPhase?: (phase: 'validating' | 'parsing' | 'ready', ratio: number) => void
    }) => uploadDataset(file, { onPhase }),
    onSuccess: (dataset: DatasetDetail) => {
      client.setQueryData(['dataset', dataset.dataset_id], dataset)
      void client.invalidateQueries({ queryKey: ['datasets'] })
    },
  })
}

export function useLoadSample() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => api.loadSample(key),
    onSuccess: (dataset) => {
      client.setQueryData(['dataset', dataset.dataset_id], dataset)
      void client.invalidateQueries({ queryKey: ['datasets'] })
    },
  })
}

export function useRun(runId: string | undefined) {
  return useQuery<RunDetail>({
    queryKey: ['run', runId],
    queryFn: () => api.getRun(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && TERMINAL_STATUSES.has(status) ? false : 1000
    },
  })
}

export function useRuns(limit = 8) {
  return useQuery({
    queryKey: ['runs', limit],
    queryFn: () => api.listRuns(limit),
    refetchInterval: 5000,
  })
}

export function useCreateRun() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { dataset_id: string; question: string; mode?: 'auto' | 'live' | 'demo' }) =>
      api.createRun(body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}
