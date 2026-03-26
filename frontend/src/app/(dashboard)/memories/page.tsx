'use client'

import { useQuery } from '@tanstack/react-query'
import { useTranslation } from '@/lib/hooks/use-translation'
import { AppShell } from '@/components/layout/AppShell'
import { memoriesApi } from '@/lib/api/memories'
import { MemoryTimeline } from './components/MemoryTimeline'

export default function MemoriesPage() {
  const { t } = useTranslation()

  // Check if Memory Hub is connected
  const { data: hubStatus } = useQuery({
    queryKey: ['memories', 'status'],
    queryFn: () => memoriesApi.status(),
    staleTime: 60 * 1000,
  })

  const isConnected = hubStatus?.connected === true

  return (
    <AppShell>
      <div className="p-4 md:p-6">
        <h1 className="text-xl md:text-2xl font-bold mb-4 md:mb-6">
          {t.memories?.browseTitle || 'Memories'}
        </h1>
        {isConnected ? (
          <MemoryTimeline />
        ) : (
          <div className="text-center py-16 text-muted-foreground">
            <p className="text-sm">
              {t.memories?.hubOffline || 'Memory Hub is not connected. Start it to browse memories.'}
            </p>
          </div>
        )}
      </div>
    </AppShell>
  )
}
