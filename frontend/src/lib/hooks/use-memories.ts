import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { memoriesApi } from '@/lib/api/memories'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { MemoryImportRequest } from '@/lib/types/memory'

export function useMemoryHubStatus() {
  return useQuery({
    queryKey: QUERY_KEYS.memoryStatus,
    queryFn: () => memoriesApi.status(),
    staleTime: 30 * 1000, // 30 seconds
    retry: 1,
  })
}

export function useMemoryBrowse(params: {
  memory_type?: string
  limit?: number
  offset?: number
  enabled?: boolean
}) {
  const { enabled = true, ...queryParams } = params
  return useQuery({
    queryKey: [...QUERY_KEYS.memoryBrowse(queryParams.memory_type || 'episodic_memory'), queryParams],
    queryFn: () => memoriesApi.browse(queryParams),
    enabled,
    staleTime: 10 * 1000,
  })
}

export function useMemorySearch(query: string, params?: {
  memory_types?: string
  retrieve_method?: string
  top_k?: number
}) {
  return useQuery({
    queryKey: [...QUERY_KEYS.memorySearch(query), params],
    queryFn: () => memoriesApi.search({ query, ...params }),
    enabled: query.length > 0,
    staleTime: 30 * 1000,
  })
}

export function useImportMemories() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: MemoryImportRequest) => memoriesApi.import(data),
    onSuccess: (data) => {
      const msg = t.memories?.importSuccess
        || `${data.success_count} memories imported as sources`
      toast({ title: msg })
      // Invalidate sources to show newly imported ones
      queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
    onError: (error: Error) => {
      toast({
        title: t.memories?.importError || 'Failed to import memories',
        description: error.message,
        variant: 'destructive',
      })
    },
  })
}
