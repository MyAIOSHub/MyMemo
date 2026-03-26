'use client'

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { Brain, RefreshCw } from 'lucide-react'
import { useMemoryHubStatus } from '@/lib/hooks/use-memories'
import { useTranslation } from '@/lib/hooks/use-translation'

export function MemoryHubCard() {
  const { t } = useTranslation()
  const { data, isLoading, refetch, isFetching } = useMemoryHubStatus()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5" />
          Memory Hub
        </CardTitle>
        <CardDescription>
          {t.memories?.hubDescription || 'Manage your Memory Hub connection for cross-application memory sharing.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Connection Status */}
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">
            {t.memories?.connectionStatus || 'Connection Status'}
          </span>
          {isLoading ? (
            <LoadingSpinner size="sm" />
          ) : data?.connected ? (
            <Badge variant="outline" className="gap-1.5">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              {t.memories?.connected || 'Connected'}
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1.5">
              <span className="h-2 w-2 rounded-full bg-red-500" />
              {t.memories?.disconnected || 'Disconnected'}
            </Badge>
          )}
        </div>

        {/* Memory Hub URL */}
        {data?.url && (
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">URL</span>
            <code className="text-sm text-muted-foreground bg-muted px-2 py-1 rounded">
              {data.url}
            </code>
          </div>
        )}

        {/* Check Connection Button */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isFetching}
          className="w-full"
        >
          {isFetching ? (
            <LoadingSpinner size="sm" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-2" />
          )}
          {t.memories?.checkConnection || 'Check Connection'}
        </Button>

        {/* Offline Hint */}
        {!isLoading && data && !data.connected && (
          <p className="text-sm text-muted-foreground">
            {t.memories?.offlineHint ||
              'Run docker compose -f docker-compose.memory-hub.yml up -d to start Memory Hub'}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
