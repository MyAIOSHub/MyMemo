'use client'

import { useMemo, useState, useCallback } from 'react'
import { useNotebookChat } from '@/lib/hooks/useNotebookChat'
import { useNotes } from '@/lib/hooks/use-notes'
import { useAsk } from '@/lib/hooks/use-ask'
import { useModelDefaults } from '@/lib/hooks/use-models'
import { ChatPanel } from '@/components/source/ChatPanel'
import { StreamingResponse } from '@/components/search/StreamingResponse'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { Card, CardContent } from '@/components/ui/card'
import { AlertCircle } from 'lucide-react'
import { ContextSelections } from '../[id]/page'
import { useTranslation } from '@/lib/hooks/use-translation'
import { SourceListResponse } from '@/lib/types/api'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'

interface ChatColumnProps {
  notebookId: string
  contextSelections: ContextSelections
  sources: SourceListResponse[]
  sourcesLoading: boolean
}

export function ChatColumn({ notebookId, contextSelections, sources, sourcesLoading }: ChatColumnProps) {
  const { t } = useTranslation()

  // Toggle states for input area
  const [isGlobalAsk, setIsGlobalAsk] = useState(false)
  const [webSearchEnabled, setWebSearchEnabled] = useState(false)

  // Fetch notes for this notebook
  const { data: notes = [], isLoading: notesLoading } = useNotes(notebookId)

  // Initialize notebook chat hook
  const chat = useNotebookChat({
    notebookId,
    sources,
    notes,
    contextSelections
  })

  // Global Ask state
  const ask = useAsk()
  const { data: modelDefaults } = useModelDefaults()

  // Column store for auto-collapse
  const { setSources, setStudio } = useNotebookColumnsStore()

  // Wrapped send handler with column auto-collapse
  const handleSendMessage = useCallback((message: string, modelOverride?: string) => {
    // Auto-collapse: collapse left, expand right when chatting
    setSources(true)
    setStudio(false)

    if (isGlobalAsk) {
      // Use global ask
      if (modelDefaults?.default_chat_model) {
        ask.sendAsk(message, {
          strategy: modelDefaults.default_chat_model,
          answer: modelDefaults.default_chat_model,
          finalAnswer: modelDefaults.default_chat_model
        })
      }
    } else {
      // Use notebook chat
      chat.sendMessage(message, modelOverride)
    }
  }, [isGlobalAsk, chat, ask, modelDefaults, setSources, setStudio])

  // Calculate context stats for indicator
  const contextStats = useMemo(() => {
    let sourcesInsights = 0
    let sourcesFull = 0
    let notesCount = 0

    sources.forEach(source => {
      const mode = contextSelections.sources[source.id]
      if (mode === 'insights') {
        sourcesInsights++
      } else if (mode === 'full') {
        sourcesFull++
      }
    })

    notes.forEach(note => {
      const mode = contextSelections.notes[note.id]
      if (mode === 'full') {
        notesCount++
      }
    })

    return {
      sourcesInsights,
      sourcesFull,
      notesCount,
      tokenCount: chat.tokenCount,
      charCount: chat.charCount
    }
  }, [sources, notes, contextSelections, chat.tokenCount, chat.charCount])

  // Show loading state while sources/notes are being fetched
  if (sourcesLoading || notesLoading) {
    return (
      <Card className="h-full flex flex-col">
        <CardContent className="flex-1 flex items-center justify-center">
          <LoadingSpinner size="lg" />
        </CardContent>
      </Card>
    )
  }

  // Show error state if data fetch failed
  if (!sources && !notes) {
    return (
      <Card className="h-full flex flex-col">
        <CardContent className="flex-1 flex items-center justify-center">
          <div className="text-center text-muted-foreground">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-sm">{t.chat.unableToLoadChat}</p>
            <p className="text-xs mt-2">{t.common.refreshPage || 'Please try refreshing the page'}</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="h-full flex flex-col min-h-0">
      {/* Unified chat — no tabs */}
      <div className="flex-1 min-h-0">
        <ChatPanel
          title={isGlobalAsk
            ? (t.chat?.globalAsk || 'Global Ask')
            : t.chat.chatWithNotebook
          }
          contextType="notebook"
          messages={isGlobalAsk ? [] : chat.messages}
          isStreaming={isGlobalAsk ? ask.isStreaming : chat.isSending}
          contextIndicators={null}
          onSendMessage={handleSendMessage}
          modelOverride={chat.currentSession?.model_override ?? chat.pendingModelOverride ?? undefined}
          onModelChange={(model) => chat.setModelOverride(model ?? null)}
          sessions={isGlobalAsk ? [] : chat.sessions}
          currentSessionId={isGlobalAsk ? null : chat.currentSessionId}
          onCreateSession={isGlobalAsk ? undefined : (title) => chat.createSession(title)}
          onSelectSession={isGlobalAsk ? undefined : chat.switchSession}
          onUpdateSession={isGlobalAsk ? undefined : (sessionId, title) => chat.updateSession(sessionId, { title })}
          onDeleteSession={isGlobalAsk ? undefined : chat.deleteSession}
          loadingSessions={isGlobalAsk ? false : chat.loadingSessions}
          notebookContextStats={isGlobalAsk ? undefined : contextStats}
          notebookId={notebookId}
          // Toggle props
          isGlobalAsk={isGlobalAsk}
          onToggleGlobalAsk={setIsGlobalAsk}
          webSearchEnabled={webSearchEnabled}
          onToggleWebSearch={setWebSearchEnabled}
          // Global ask streaming response
          globalAskResponse={isGlobalAsk ? {
            isStreaming: ask.isStreaming,
            strategy: ask.strategy,
            answers: ask.answers,
            finalAnswer: ask.finalAnswer
          } : undefined}
        />
      </div>
    </div>
  )
}
