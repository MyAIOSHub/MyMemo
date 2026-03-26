'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Brain, Globe, Terminal, Loader2 } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { memoriesApi } from '@/lib/api/memories'

type OriginFilter = 'all' | 'browser' | 'claude_code' | 'evermemo'

const MEMORY_TYPES = ['episodic_memory', 'event_log', 'foresight'] as const

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

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return ''
  return new Date(ts).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function MemoryTimeline() {
  const { t } = useTranslation()
  const [originFilter, setOriginFilter] = useState<OriginFilter>('all')
  const [activeType, setActiveType] = useState<string>('episodic_memory')

  // Fetch memories directly from Memory Hub
  const { data, isLoading } = useQuery({
    queryKey: ['memories', 'browse', activeType],
    queryFn: () => memoriesApi.browse({ memory_type: activeType, limit: 50 }),
    staleTime: 30 * 1000,
  })

  const memories = data?.memories || []

  // Apply origin filter
  const filteredMemories = useMemo(() => {
    if (originFilter === 'all') return memories
    return memories.filter((m) => m.source_origin === originFilter)
  }, [memories, originFilter])

  const typeLabels: Record<string, string> = {
    episodic_memory: t.memories?.episodicMemory || 'Episodic Memory',
    event_log: t.memories?.eventLog || 'Event Log',
    foresight: t.memories?.foresight || 'Foresight',
  }

  const filterOptions: { value: OriginFilter; label: string; icon: React.ReactNode }[] = [
    { value: 'all', label: t.memories?.filterAll || 'All', icon: null },
    { value: 'browser', label: t.memories?.originBrowser || 'Browser', icon: <Globe className="h-3.5 w-3.5" /> },
    { value: 'claude_code', label: t.memories?.originClaudeCode || 'Claude Code', icon: <Terminal className="h-3.5 w-3.5" /> },
    { value: 'evermemo', label: t.memories?.originEvermemo || 'EverMemo', icon: <Brain className="h-3.5 w-3.5" /> },
  ]

  return (
    <div className="space-y-6">
      {/* Memory type tabs */}
      <div className="flex flex-wrap gap-2 border-b pb-3">
        {MEMORY_TYPES.map((type) => (
          <Button
            key={type}
            variant={activeType === type ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setActiveType(type)}
          >
            {typeLabels[type] || type}
          </Button>
        ))}
      </div>

      {/* Origin filter */}
      <div className="flex flex-wrap gap-2">
        {filterOptions.map((opt) => (
          <Button
            key={opt.value}
            variant={originFilter === opt.value ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => setOriginFilter(opt.value)}
            className="gap-1.5"
          >
            {opt.icon}
            {opt.label}
          </Button>
        ))}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty state */}
      {!isLoading && filteredMemories.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <Brain className="h-10 w-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">
            {t.memories?.noMemories || 'No memories found.'}
          </p>
        </div>
      )}

      {/* Timeline */}
      {!isLoading && filteredMemories.length > 0 && (
        <div className="relative ml-4">
          {/* Vertical line */}
          <div className="absolute left-0 top-0 bottom-0 w-px bg-border" />

          <div className="space-y-4">
            {filteredMemories.map((memory) => (
              <div key={memory.id} className="relative pl-8">
                {/* Dot on timeline */}
                <div className="absolute left-0 top-2 -translate-x-1/2 w-3 h-3 rounded-full bg-primary border-2 border-background" />

                <div className="border rounded-lg p-4 hover:border-primary/50 hover:bg-accent/30 transition-colors">
                  {/* Header: title + origin */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <h3 className="text-sm font-medium line-clamp-2">
                      {memory.title || 'Untitled'}
                    </h3>
                    {memory.source_origin && (
                      <OriginBadge origin={memory.source_origin} />
                    )}
                  </div>

                  {/* Summary */}
                  {memory.summary && (
                    <p className="text-xs text-muted-foreground line-clamp-3 mb-2">
                      {memory.summary}
                    </p>
                  )}

                  {/* Footer: timestamp + type + group */}
                  <div className="flex items-center gap-2 flex-wrap">
                    {memory.timestamp && (
                      <span className="text-xs text-muted-foreground">
                        {formatTimestamp(memory.timestamp)}
                      </span>
                    )}
                    <Badge variant="secondary" className="text-xs">
                      {typeLabels[memory.memory_type] || memory.memory_type}
                    </Badge>
                    {memory.group_name && (
                      <span className="text-xs text-muted-foreground truncate max-w-48">
                        {memory.group_name}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
