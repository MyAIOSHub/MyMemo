export interface MemoryItem {
  id: string
  memory_type: string
  title: string
  summary?: string | null
  content: string
  timestamp?: string | null
  source_origin: string // 'browser' | 'claude_code' | 'evermemo'
  group_id?: string | null
  group_name?: string | null
  participants?: string[] | null
  keywords?: string[] | null
  score?: number
}

export interface MemoryBrowseResponse {
  memories: MemoryItem[]
  total_count: number
  has_more: boolean
}

export interface MemorySearchResponse {
  memories: MemoryItem[]
  total_count: number
  has_more: boolean
}

export interface MemoryImportRequest {
  memory_ids: string[]
  memory_type: string
  notebook_id: string
  user_id?: string
}

export interface MemoryImportResult {
  memory_id: string
  source_id?: string | null
  title?: string | null
  status: string
  error?: string | null
}

export interface MemoryImportResponse {
  imported: MemoryImportResult[]
  total: number
  success_count: number
}

export interface MemoryHubStatus {
  connected: boolean
  status_code?: number
  url: string
  error?: string
}
