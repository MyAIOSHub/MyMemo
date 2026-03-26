'use client'

import { PodcastEpisode, ACTIVE_EPISODE_STATUSES, FAILED_EPISODE_STATUSES } from '@/lib/types/podcasts'
import { EmptyState } from '@/components/common/EmptyState'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { Badge } from '@/components/ui/badge'
import { Mic, Play, Loader2, AlertCircle, Clock } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { getDateLocale } from '@/lib/utils/date-locale'
import { useTranslation } from '@/lib/hooks/use-translation'

interface WorksListProps {
  episodes: PodcastEpisode[]
  isLoading: boolean
}

function getStatusBadge(status: string | null | undefined) {
  const s = status ?? 'unknown'

  if (s === 'completed') {
    return <Badge variant="default" className="bg-green-600 hover:bg-green-700 text-xs">completed</Badge>
  }
  if (ACTIVE_EPISODE_STATUSES.includes(s as never)) {
    return (
      <Badge variant="secondary" className="text-xs">
        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
        {s}
      </Badge>
    )
  }
  if (FAILED_EPISODE_STATUSES.includes(s as never)) {
    return (
      <Badge variant="destructive" className="text-xs">
        <AlertCircle className="h-3 w-3 mr-1" />
        failed
      </Badge>
    )
  }

  return <Badge variant="outline" className="text-xs">{s}</Badge>
}

export function WorksList({ episodes, isLoading }: WorksListProps) {
  const { t, language } = useTranslation()

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">{t.common.works}</h2>
        <div className="flex items-center justify-center py-12">
          <LoadingSpinner size="lg" />
        </div>
      </div>
    )
  }

  if (!episodes || episodes.length === 0) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">{t.common.works}</h2>
        <EmptyState
          icon={Mic}
          title={t.common.noWorksYet}
          description={t.common.noWorksDesc}
        />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold">{t.common.works}</h2>
        <span className="text-sm text-muted-foreground">({episodes.length})</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {episodes.map((episode) => (
          <div
            key={episode.id}
            className="group relative rounded-lg border bg-card p-4 shadow-sm transition-colors hover:bg-accent/50"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <h3 className="font-medium text-sm truncate">{episode.name}</h3>
                <p className="text-xs text-muted-foreground mt-1 truncate">
                  {episode.episode_profile?.name}
                </p>
              </div>
              {getStatusBadge(episode.job_status)}
            </div>

            <div className="flex items-center justify-between mt-3">
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" />
                {episode.created ? (
                  formatDistanceToNow(new Date(episode.created), {
                    addSuffix: true,
                    locale: getDateLocale(language),
                  })
                ) : (
                  '—'
                )}
              </div>

              {episode.audio_url && episode.job_status === 'completed' && (
                <a
                  href={episode.audio_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  <Play className="h-3.5 w-3.5 fill-current" />
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
