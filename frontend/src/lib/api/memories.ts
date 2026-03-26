import apiClient from './client'
import type {
  MemoryBrowseResponse,
  MemorySearchResponse,
  MemoryImportRequest,
  MemoryImportResponse,
  MemoryHubStatus,
} from '@/lib/types/memory'

export const memoriesApi = {
  status: async (): Promise<MemoryHubStatus> => {
    const response = await apiClient.get<MemoryHubStatus>('/memories/status')
    return response.data
  },

  browse: async (params: {
    user_id?: string
    memory_type?: string
    limit?: number
    offset?: number
    start_time?: string
    end_time?: string
  }): Promise<MemoryBrowseResponse> => {
    const response = await apiClient.get<MemoryBrowseResponse>('/memories/browse', { params })
    return response.data
  },

  search: async (params: {
    query: string
    user_id?: string
    memory_types?: string
    retrieve_method?: string
    top_k?: number
  }): Promise<MemorySearchResponse> => {
    const response = await apiClient.get<MemorySearchResponse>('/memories/search', { params })
    return response.data
  },

  import: async (data: MemoryImportRequest): Promise<MemoryImportResponse> => {
    const response = await apiClient.post<MemoryImportResponse>('/memories/import', data)
    return response.data
  },
}
