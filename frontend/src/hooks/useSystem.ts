import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'

export function useConfig() {
  return useQuery({
    queryKey: ['system', 'config'],
    queryFn: api.config,
    staleTime: 5 * 60_000,
  })
}

export function useHealth() {
  return useQuery({
    queryKey: ['system', 'health'],
    queryFn: api.health,
    staleTime: 15_000,
    refetchInterval: 30_000,
  })
}
