'use client'

import { useState, useMemo, useEffect, useRef } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Loader2, Search, Brain, Globe, Terminal, Import } from 'lucide-react'
import { useMemoryBrowse, useMemorySearch, useImportMemories, useMemoryHubStatus } from '@/lib/hooks/use-memories'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { MemoryItem } from '@/lib/types/memory'

interface MemoryBrowserProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  notebookId: string
}

const MEMORY_TYPE_VALUES = ['episodic_memory', 'event_log', 'foresight'] as const

const MEMORY_TYPE_LABELS: Record<string, string> = {
  episodic_memory: 'Episodic Memory',
  event_log: 'Event Log',
  foresight: 'Foresight',
}

function getMemoryTypeLabel(value: string, t: any): string {
  const key = value === 'episodic_memory' ? 'episodicMemory'
    : value === 'event_log' ? 'eventLog'
    : 'foresight'
  return t.memories?.[key] || MEMORY_TYPE_LABELS[value] || value
}

function OriginIcon({ origin }: { origin: string }) {
  switch (origin) {
    case 'browser':
      return <Globe className="h-3.5 w-3.5" />
    case 'claude_code':
      return <Terminal className="h-3.5 w-3.5" />
    default:
      return <Brain className="h-3.5 w-3.5" />
  }
}

function OriginBadge({ origin }: { origin: string }) {
  const labels: Record<string, string> = {
    browser: 'Browser',
    claude_code: 'Claude Code',
    evermemo: 'EverMemo',
  }
  const colors: Record<string, string> = {
    browser: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
    claude_code: 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
    evermemo: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  }

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${colors[origin] || colors.evermemo}`}>
      <OriginIcon origin={origin} />
      {labels[origin] || origin}
    </span>
  )
}

function MemoryCard({
  memory,
  selected,
  onToggle,
}: {
  memory: MemoryItem
  selected: boolean
  onToggle: () => void
}) {
  const timestamp = memory.timestamp
    ? new Date(memory.timestamp).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : null

  return (
    <div
      className={`border rounded-lg p-3 cursor-pointer transition-colors ${
        selected
          ? 'border-primary bg-primary/5'
          : 'border-border hover:border-primary/50'
      }`}
      onClick={onToggle}
    >
      <div className="flex items-start gap-3">
        <Checkbox
          checked={selected}
          onCheckedChange={onToggle}
          className="mt-1"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="text-sm font-medium truncate">{memory.title}</h4>
            <OriginBadge origin={memory.source_origin} />
          </div>
          {memory.summary && (
            <p className="text-xs text-muted-foreground line-clamp-2">
              {memory.summary}
            </p>
          )}
          <div className="flex items-center gap-2 mt-1.5">
            {timestamp && (
              <span className="text-xs text-muted-foreground">{timestamp}</span>
            )}
            {memory.group_name && (
              <span className="text-xs text-muted-foreground">
                {memory.group_name}
              </span>
            )}
            {memory.score !== undefined && (
              <Badge variant="outline" className="text-xs">
                {(memory.score * 100).toFixed(0)}%
              </Badge>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export function MemoryBrowser({ open, onOpenChange, notebookId }: MemoryBrowserProps) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState('episodic_memory')
  const [searchInput, setSearchInput] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Debounce search: wait 400ms after user stops typing
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(searchInput.trim())
    }, 400)
    return () => clearTimeout(debounceRef.current)
  }, [searchInput])

  const isSearching = debouncedQuery.length > 0

  // Browse query (when not searching)
  const browseQuery = useMemoryBrowse({
    memory_type: activeTab,
    limit: 50,
    enabled: open && !isSearching,
  })

  // Search query (fires only after debounce, minimum 2 chars)
  const searchResult = useMemorySearch(
    debouncedQuery.length >= 2 ? debouncedQuery : '',
    {
      memory_types: activeTab,
      retrieve_method: 'hybrid',
      top_k: 30,
    }
  )

  const importMemories = useImportMemories()

  const memories = useMemo(() => {
    if (isSearching) {
      return searchResult.data?.memories || []
    }
    return browseQuery.data?.memories || []
  }, [isSearching, searchResult.data, browseQuery.data])

  const isLoading = isSearching ? searchResult.isLoading : browseQuery.isLoading

  const toggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleImport = () => {
    if (selectedIds.size === 0) return
    importMemories.mutate(
      {
        memory_ids: Array.from(selectedIds),
        memory_type: activeTab,
        notebook_id: notebookId,
      },
      {
        onSuccess: () => {
          setSelectedIds(new Set())
          onOpenChange(false)
        },
      }
    )
  }

  const handleTabChange = (tab: string) => {
    setActiveTab(tab)
    setSelectedIds(new Set())
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            {t.memories?.browseTitle || 'Browse Memories'}
          </DialogTitle>
        </DialogHeader>

        {/* Search bar */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={t.memories?.searchPlaceholder || 'Search your memories...'}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Memory type tabs */}
        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList className="grid w-full grid-cols-3">
            {MEMORY_TYPE_VALUES.map((value) => (
              <TabsTrigger key={value} value={value}>
                {getMemoryTypeLabel(value, t)}
              </TabsTrigger>
            ))}
          </TabsList>

          {MEMORY_TYPE_VALUES.map((value) => (
            <TabsContent key={value} value={value} className="mt-0">
              {/* Memory list */}
              <div className="flex-1 overflow-y-auto max-h-[45vh] space-y-2 py-2">
                {isLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : memories.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground text-sm">
                    {isSearching
                      ? 'No memories found for this query'
                      : 'No memories available'}
                  </div>
                ) : (
                  memories.map((memory) => (
                    <MemoryCard
                      key={memory.id}
                      memory={memory}
                      selected={selectedIds.has(memory.id)}
                      onToggle={() => toggleSelection(memory.id)}
                    />
                  ))
                )}
              </div>
            </TabsContent>
          ))}
        </Tabs>

        <DialogFooter className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            {selectedIds.size > 0
              ? `${selectedIds.size} selected`
              : `${memories.length} memories`}
          </span>
          <Button
            onClick={handleImport}
            disabled={selectedIds.size === 0 || importMemories.isPending}
          >
            {importMemories.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Import className="h-4 w-4 mr-2" />
            )}
            {t.memories?.importSelected || 'Import Selected'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
