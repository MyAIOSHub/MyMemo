'use client'

import { useMemo, useState, useCallback } from 'react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
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
  Lightbulb,
  BookOpen,
  ClipboardList,
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
import { ModelSelector } from '@/components/source/ModelSelector'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MermaidDiagram } from '@/components/common/MermaidDiagram'
import type { SourceListResponse, NoteResponse } from '@/lib/types/api'
import type { ContextSelections } from '../[id]/page'

interface StudioItem {
  icon: LucideIcon
  labelKey: string
  transformationName?: string
  action?: 'podcast' | 'summary'
}

// Sub-items inside the "Summary" card
interface SummarySubItem {
  icon: LucideIcon
  labelKey: string
  transformationName: string
}

const SUMMARY_SUB_ITEMS: SummarySubItem[] = [
  { icon: FileText, labelKey: 'simpleSummary', transformationName: 'Simple Summary' },
  { icon: BookOpen, labelKey: 'denseSummary', transformationName: 'Dense Summary' },
  { icon: Lightbulb, labelKey: 'keyInsights', transformationName: 'Key Insights' },
  { icon: AudioLines, labelKey: 'audioOverview', transformationName: 'audio-overview' },
  { icon: Video, labelKey: 'videoSummary', transformationName: 'video-summary' },
]

const STUDIO_ITEMS: StudioItem[] = [
  { icon: ClipboardList, labelKey: 'summary', action: 'summary' },
  { icon: Monitor, labelKey: 'presentation', transformationName: 'presentation' },
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

  // Summary picker dialog
  const [summaryPickerOpen, setSummaryPickerOpen] = useState(false)

  // Confirmation dialog state
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false)
  const [pendingItem, setPendingItem] = useState<{ labelKey: string; transformationName: string } | null>(null)
  const [selectedModel, setSelectedModel] = useState<string | undefined>(undefined)

  // Generation state
  const [activeResult, setActiveResult] = useState<{ transformationName: string; output: string } | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [generatingItem, setGeneratingItem] = useState<string | null>(null)

  const { data: transformations } = useTransformations()
  const { data: modelDefaults } = useModelDefaults()

  const collapseButton = useMemo(
    () => createCollapseButton(toggleStudio, t.studio?.title || 'Studio', 'right'),
    [toggleStudio, t.studio?.title]
  )

  const studioTranslations: Record<string, string> = t.studio || {}

  // Handle card click
  const handleItemClick = (item: StudioItem) => {
    if (item.action === 'podcast') {
      setPodcastDialogOpen(true)
      return
    }

    if (item.action === 'summary') {
      setSummaryPickerOpen(true)
      return
    }

    const transformation = transformations?.find(tr => tr.name === item.transformationName)
    if (!transformation) {
      toast.error(t.studio?.transformationNotFound || 'Transformation not found')
      return
    }

    // Open confirm dialog
    setPendingItem({ labelKey: item.labelKey, transformationName: item.transformationName! })
    setSelectedModel(modelDefaults?.default_chat_model || undefined)
    setConfirmDialogOpen(true)
  }

  // Handle summary sub-item selection
  const handleSummarySelect = (subItem: SummarySubItem) => {
    const transformation = transformations?.find(tr => tr.name === subItem.transformationName)
    if (!transformation) {
      toast.error(t.studio?.transformationNotFound || 'Transformation not found')
      return
    }

    setSummaryPickerOpen(false)
    setPendingItem({ labelKey: subItem.labelKey, transformationName: subItem.transformationName })
    setSelectedModel(modelDefaults?.default_chat_model || undefined)
    setConfirmDialogOpen(true)
  }

  // Execute after user confirms in dialog
  const handleConfirmGenerate = useCallback(async () => {
    if (!pendingItem) return

    const transformation = transformations?.find(tr => tr.name === pendingItem.transformationName)
    if (!transformation) return

    setConfirmDialogOpen(false)
    setIsGenerating(true)
    setGeneratingItem(pendingItem.labelKey)

    try {
      // Build context
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

      const inputParts: string[] = []
      contextResult.context.sources?.forEach((s: Record<string, unknown>) => {
        const text = (s.full_text || s.content || '') as string
        if (text) inputParts.push(text)
      })
      contextResult.context.notes?.forEach((n: Record<string, unknown>) => {
        if (n.content) inputParts.push(n.content as string)
      })
      const inputText = inputParts.join('\n\n---\n\n')

      if (!inputText.trim()) {
        toast.warning(t.studio?.noContent || 'No content available')
        return
      }

      const modelId = selectedModel || modelDefaults?.default_chat_model
      if (!modelId) {
        toast.error(t.studio?.selectModel || 'Please select a model first')
        return
      }

      const result = await transformationsApi.execute({
        transformation_id: transformation.id,
        input_text: inputText,
        model_id: modelId,
      })

      setActiveResult({ transformationName: pendingItem.transformationName, output: result.output })
      toast.success(t.studio?.generationComplete || 'Generation complete')
    } catch (err) {
      console.error('Studio generation failed:', err)
      toast.error(t.studio?.generationFailed || 'Generation failed')
    } finally {
      setIsGenerating(false)
      setGeneratingItem(null)
      setPendingItem(null)
    }
  }, [pendingItem, transformations, sources, notes, contextSelections, notebookId, selectedModel, modelDefaults, t])

  // Find label for active result (check both STUDIO_ITEMS and SUMMARY_SUB_ITEMS)
  const activeResultLabel = activeResult
    ? (() => {
        const mainItem = STUDIO_ITEMS.find(item => item.transformationName === activeResult.transformationName)
        if (mainItem) return studioTranslations[mainItem.labelKey] || activeResult.transformationName
        const subItem = SUMMARY_SUB_ITEMS.find(item => item.transformationName === activeResult.transformationName)
        if (subItem) return studioTranslations[subItem.labelKey] || activeResult.transformationName
        return activeResult.transformationName
      })()
    : ''

  const pendingItemLabel = pendingItem
    ? studioTranslations[pendingItem.labelKey] || pendingItem.labelKey
    : ''

  // Check if summary card should be available (at least one sub-item has a transformation)
  const isSummaryAvailable = SUMMARY_SUB_ITEMS.some(
    sub => transformations?.some(tr => tr.name === sub.transformationName)
  )

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
            {/* Studio card grid */}
            <div className="grid grid-cols-2 gap-2 mb-6">
              {STUDIO_ITEMS.map((item) => {
                const Icon = item.icon
                const label = studioTranslations[item.labelKey] || item.labelKey
                const isPodcast = item.action === 'podcast'
                const isSummary = item.action === 'summary'
                const isItemGenerating = isGenerating && generatingItem === item.labelKey
                const isAvailable = isPodcast
                  || isSummary ? isSummaryAvailable
                  : !!(item.transformationName && transformations?.some(tr => tr.name === item.transformationName))
                return (
                  <button
                    key={item.labelKey}
                    className={`flex flex-col items-start gap-1.5 p-2 rounded-lg border transition-colors group text-left overflow-hidden ${
                      !isAvailable
                        ? 'opacity-40 cursor-not-allowed bg-muted/50 border-border'
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
                  {activeResult.transformationName === 'mind-map' ? (
                    <MermaidDiagram code={activeResult.output} />
                  ) : (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {activeResult.output}
                    </ReactMarkdown>
                  )}
                </div>
              </div>
            )}

            {/* Empty state */}
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

      {/* Summary type picker dialog */}
      <Dialog open={summaryPickerOpen} onOpenChange={setSummaryPickerOpen}>
        <DialogContent className="sm:max-w-[360px]">
          <DialogTitle>{studioTranslations.summary || 'Summary'}</DialogTitle>
          <DialogDescription>
            {studioTranslations.chooseSummaryType || 'Choose summary type'}
          </DialogDescription>

          <div className="grid grid-cols-1 gap-2 py-2">
            {SUMMARY_SUB_ITEMS.map((subItem) => {
              const SubIcon = subItem.icon
              const subLabel = studioTranslations[subItem.labelKey] || subItem.labelKey
              const hasTransformation = transformations?.some(tr => tr.name === subItem.transformationName)
              return (
                <button
                  key={subItem.labelKey}
                  className={`flex items-center gap-3 p-3 rounded-lg border transition-colors text-left ${
                    hasTransformation
                      ? 'bg-primary/5 border-primary/20 hover:bg-primary/10 cursor-pointer'
                      : 'opacity-40 cursor-not-allowed bg-muted/50 border-border'
                  }`}
                  onClick={() => hasTransformation && handleSummarySelect(subItem)}
                  disabled={!hasTransformation}
                >
                  <SubIcon className={`h-4 w-4 flex-shrink-0 ${
                    hasTransformation ? 'text-primary' : 'text-muted-foreground/50'
                  }`} />
                  <span className={`text-sm font-medium ${
                    hasTransformation ? 'text-foreground' : 'text-muted-foreground/50'
                  }`}>
                    {subLabel}
                  </span>
                </button>
              )
            })}
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirmation dialog for generation */}
      <Dialog open={confirmDialogOpen} onOpenChange={setConfirmDialogOpen}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogTitle>{pendingItemLabel}</DialogTitle>
          <DialogDescription>
            {t.studio?.description || 'Generate content from your sources'}
          </DialogDescription>

          <div className="space-y-4 py-2">
            {/* Model selector */}
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{t.chat?.model || 'Model'}</span>
              <ModelSelector
                currentModel={selectedModel}
                onModelChange={(model) => setSelectedModel(model)}
              />
            </div>

            {/* Source count info */}
            <div className="text-xs text-muted-foreground">
              {t.navigation?.sources || 'Sources'}: {sources?.filter(s => {
                const mode = contextSelections?.sources[s.id]
                return mode !== 'off'
              }).length || 0}
              {' | '}
              {t.common?.notes || 'Notes'}: {notes?.filter(n => {
                const mode = contextSelections?.notes[n.id]
                return mode !== 'off'
              }).length || 0}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDialogOpen(false)}>
              {t.common?.cancel || 'Cancel'}
            </Button>
            <Button onClick={handleConfirmGenerate} disabled={!selectedModel}>
              <Sparkles className="h-4 w-4 mr-2" />
              {t.studio?.generate || 'Generate'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Podcast generation dialog */}
      <GeneratePodcastDialog
        open={podcastDialogOpen}
        onOpenChange={setPodcastDialogOpen}
      />
    </>
  )
}
