'use client'

import { useMemo, useState } from 'react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  AudioLines,
  Monitor,
  Video,
  GitBranch,
  FileText,
  Layers,
  CircleHelp,
  BarChart3,
  Table,
  Sparkles,
  Mic,
  Loader2,
  X,
  LucideIcon,
} from 'lucide-react'
import { CollapsibleColumn, createCollapseButton } from '@/components/notebooks/CollapsibleColumn'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import { useTranslation } from '@/lib/hooks/use-translation'
import { GeneratePodcastDialog } from '@/components/podcasts/GeneratePodcastDialog'
import { toast } from 'sonner'
import { chatApi } from '@/lib/api/chat'
import { transformationsApi } from '@/lib/api/transformations'
import { useTransformations } from '@/lib/hooks/use-transformations'
import { useModelDefaults } from '@/lib/hooks/use-models'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { SourceListResponse, NoteResponse } from '@/lib/types/api'
import type { ContextSelections } from '../[id]/page'

interface StudioItem {
  icon: LucideIcon
  labelKey: string
  transformationName?: string
  action?: 'podcast'
}

const STUDIO_ITEMS: StudioItem[] = [
  { icon: AudioLines, labelKey: 'audioOverview', transformationName: 'audio-overview' },
  { icon: Monitor, labelKey: 'presentation', transformationName: 'presentation' },
  { icon: Video, labelKey: 'videoSummary', transformationName: 'video-summary' },
  { icon: GitBranch, labelKey: 'mindMap', transformationName: 'mind-map' },
  { icon: FileText, labelKey: 'report', transformationName: 'Analyze Paper' },
  { icon: Layers, labelKey: 'flashcards', transformationName: 'flashcards' },
  { icon: CircleHelp, labelKey: 'quiz', transformationName: 'Reflections' },
  { icon: BarChart3, labelKey: 'infographic', transformationName: 'infographic' },
  { icon: Table, labelKey: 'dataTable', transformationName: 'data-table' },
  { icon: Mic, labelKey: 'generatePodcast', action: 'podcast' },
]

interface StudioColumnProps {
  notebookId: string
  sources?: SourceListResponse[]
  notes?: NoteResponse[]
  contextSelections?: ContextSelections
}

export function StudioColumn({ notebookId, sources, notes, contextSelections }: StudioColumnProps) {
  const { t } = useTranslation()
  const { studioCollapsed, toggleStudio } = useNotebookColumnsStore()
  const [podcastDialogOpen, setPodcastDialogOpen] = useState(false)
  const [activeResult, setActiveResult] = useState<{ transformationName: string; output: string } | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [generatingItem, setGeneratingItem] = useState<string | null>(null)
  const [selectedModel] = useState<string | null>(null)

  const { data: transformations } = useTransformations()
  const { data: modelDefaults } = useModelDefaults()

  const collapseButton = useMemo(
    () => createCollapseButton(toggleStudio, t.studio?.title || 'Studio', 'right'),
    [toggleStudio, t.studio?.title]
  )

  const studioTranslations: Record<string, string> = t.studio || {}

  const handleItemClick = async (item: StudioItem) => {
    if (item.action === 'podcast') {
      setPodcastDialogOpen(true)
      return
    }

    // Find matching transformation
    const transformation = transformations?.find(tr => tr.name === item.transformationName)
    if (!transformation) {
      toast.error(t.studio?.transformationNotFound || 'Transformation not found')
      return
    }

    // Check if sources exist
    if (!sources || sources.length === 0) {
      toast.warning(t.studio?.noContent || 'Add sources first')
      return
    }

    setIsGenerating(true)
    setGeneratingItem(item.labelKey)
    try {
      // Build context config from selections
      // Default to 'full content' if no selection exists (user hasn't toggled context off)
      const contextConfig: Record<string, string> = {}
      sources?.forEach(s => {
        const mode = contextSelections?.sources[s.id]
        if (mode === 'off') {
          contextConfig[s.id] = 'not in'
        } else if (mode === 'insights') {
          contextConfig[s.id] = 'insights'
        } else {
          contextConfig[s.id] = 'full content'
        }
      })
      const noteConfig: Record<string, string> = {}
      notes?.forEach(n => {
        const mode = contextSelections?.notes[n.id]
        noteConfig[n.id] = mode === 'off' ? 'not in' : 'full content'
      })

      const contextResult = await chatApi.buildContext({
        notebook_id: notebookId,
        context_config: { sources: contextConfig, notes: noteConfig },
      })

      // Combine context into input text
      const inputParts: string[] = []
      contextResult.context.sources?.forEach((s: Record<string, unknown>) => {
        if (s.content) inputParts.push(s.content as string)
      })
      contextResult.context.notes?.forEach((n: Record<string, unknown>) => {
        if (n.content) inputParts.push(n.content as string)
      })
      const inputText = inputParts.join('\n\n---\n\n')

      if (!inputText.trim()) {
        toast.warning(t.studio?.noContent || 'No content available')
        setIsGenerating(false)
        setGeneratingItem(null)
        return
      }

      // Resolve model
      const modelId = selectedModel || modelDefaults?.default_chat_model
      if (!modelId) {
        toast.error(t.studio?.selectModel || 'Please select a model first')
        setIsGenerating(false)
        setGeneratingItem(null)
        return
      }

      // Execute transformation
      const result = await transformationsApi.execute({
        transformation_id: transformation.id,
        input_text: inputText,
        model_id: modelId,
      })

      setActiveResult({ transformationName: item.transformationName!, output: result.output })
      toast.success(t.studio?.generationComplete || 'Generation complete')
    } catch (err) {
      console.error('Studio generation failed:', err)
      toast.error(t.studio?.generationFailed || 'Generation failed')
    } finally {
      setIsGenerating(false)
      setGeneratingItem(null)
    }
  }

  // Find the labelKey for the active result to display a localized title
  const activeResultLabel = activeResult
    ? studioTranslations[
        STUDIO_ITEMS.find(item => item.transformationName === activeResult.transformationName)?.labelKey || ''
      ] || activeResult.transformationName
    : ''

  return (
    <>
      <CollapsibleColumn
        isCollapsed={studioCollapsed}
        onToggle={toggleStudio}
        collapsedIcon={Sparkles}
        collapsedLabel={t.studio?.title || 'Studio'}
        direction="right"
      >
        <Card className="h-full flex flex-col flex-1 overflow-hidden">
          <CardHeader className="pb-2 flex-shrink-0">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">{t.studio?.title || 'Studio'}</h3>
              {collapseButton}
            </div>
          </CardHeader>

          <CardContent className="flex-1 overflow-y-auto min-h-0">
            {/* Studio output grid */}
            <div className="grid grid-cols-2 gap-2 mb-6">
              {STUDIO_ITEMS.map((item) => {
                const Icon = item.icon
                const label = studioTranslations[item.labelKey] || item.labelKey
                const isPodcast = item.action === 'podcast'
                const isItemGenerating = isGenerating && generatingItem === item.labelKey
                // Check if this card has a matching transformation in the database
                const hasTransformation = isPodcast || (item.transformationName && transformations?.some(tr => tr.name === item.transformationName))
                const isAvailable = hasTransformation === true
                return (
                  <button
                    key={item.labelKey}
                    className={`flex flex-col items-start gap-1.5 p-2 rounded-lg border transition-colors group text-left overflow-hidden ${
                      !isAvailable
                        ? 'opacity-40 cursor-not-allowed bg-muted/50 border-border'
                        : isItemGenerating
                          ? 'bg-primary/5 border-primary/20 hover:bg-primary/10 cursor-pointer'
                          : 'bg-primary/5 border-primary/20 hover:bg-primary/10 cursor-pointer'
                    }`}
                    onClick={() => isAvailable && handleItemClick(item)}
                    disabled={isGenerating || !isAvailable}
                  >
                    {isItemGenerating ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary flex-shrink-0" />
                    ) : (
                      <Icon className={`h-3.5 w-3.5 transition-colors flex-shrink-0 ${
                        isAvailable
                          ? 'text-primary group-hover:text-primary'
                          : 'text-muted-foreground/50'
                      }`} />
                    )}
                    <span className={`text-[11px] font-medium transition-colors leading-tight truncate w-full ${
                      isAvailable
                        ? 'text-primary group-hover:text-primary'
                        : 'text-muted-foreground/50'
                    }`}>
                      {label}
                    </span>
                  </button>
                )
              })}
            </div>

            {/* Generation loading state */}
            {isGenerating && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                <span className="ml-2 text-sm text-muted-foreground">
                  {t.studio?.generating || 'Generating...'}
                </span>
              </div>
            )}

            {/* Generation result */}
            {activeResult && !isGenerating && (
              <div className="mt-4 border rounded-lg p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium">{activeResultLabel}</h4>
                  <Button variant="ghost" size="sm" onClick={() => setActiveResult(null)}>
                    <X className="h-3 w-3" />
                  </Button>
                </div>
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {activeResult.output}
                  </ReactMarkdown>
                </div>
              </div>
            )}

            {/* Empty state — only show when no result and not generating */}
            {!activeResult && !isGenerating && (
              <div className="flex flex-col items-center justify-center text-center py-6 px-2">
                <Sparkles className="h-6 w-6 text-muted-foreground/50 mb-2" />
                <p className="text-xs font-medium text-muted-foreground">
                  {t.studio?.emptyState || 'Studio outputs will appear here.'}
                </p>
                <p className="text-[11px] text-muted-foreground/70 mt-1 leading-relaxed">
                  {t.studio?.emptyStateDesc || 'Add sources, then click to generate audio overviews, study guides, mind maps, and more!'}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </CollapsibleColumn>

      {/* Podcast generation dialog */}
      <GeneratePodcastDialog
        open={podcastDialogOpen}
        onOpenChange={setPodcastDialogOpen}
      />
    </>
  )
}
