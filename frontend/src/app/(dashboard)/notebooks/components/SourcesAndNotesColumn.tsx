'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { SourceListResponse, NoteResponse } from '@/lib/types/api'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Plus, FileText, StickyNote, Link2, ChevronDown, Loader2, Brain, Bot, User, MoreVertical, Trash2 } from 'lucide-react'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import { AddSourceDialog } from '@/components/sources/AddSourceDialog'
import { AddExistingSourceDialog } from '@/components/sources/AddExistingSourceDialog'
import { MemoryBrowser } from '@/components/source/MemoryBrowser'
import { useMemoryHubStatus } from '@/lib/hooks/use-memories'
import { SourceCard } from '@/components/sources/SourceCard'
import { useDeleteSource, useRetrySource, useRemoveSourceFromNotebook } from '@/lib/hooks/use-sources'
import { useDeleteNote } from '@/lib/hooks/use-notes'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { useModalManager } from '@/lib/hooks/use-modal-manager'
import { ContextMode } from '../[id]/page'
import { CollapsibleColumn, createCollapseButton } from '@/components/notebooks/CollapsibleColumn'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import { useTranslation } from '@/lib/hooks/use-translation'
import { NoteEditorDialog } from './NoteEditorDialog'
import { Badge } from '@/components/ui/badge'
import { ContextToggle } from '@/components/common/ContextToggle'
import { formatDistanceToNow } from 'date-fns'
import { getDateLocale } from '@/lib/utils/date-locale'
import { useRef, useCallback, useEffect, useMemo } from 'react'

type FilterType = 'all' | 'sources' | 'memories' | 'notes'

interface SourcesAndNotesColumnProps {
  sources?: SourceListResponse[]
  sourcesLoading: boolean
  notes?: NoteResponse[]
  notesLoading: boolean
  notebookId: string
  notebookName?: string
  onRefreshSources?: () => void
  sourceContextSelections?: Record<string, ContextMode>
  noteContextSelections?: Record<string, ContextMode>
  onSourceContextModeChange?: (sourceId: string, mode: ContextMode) => void
  onNoteContextModeChange?: (noteId: string, mode: ContextMode) => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  fetchNextPage?: () => void
}

export function SourcesAndNotesColumn({
  sources,
  sourcesLoading,
  notes,
  notesLoading,
  notebookId,
  onRefreshSources,
  sourceContextSelections,
  noteContextSelections,
  onSourceContextModeChange,
  onNoteContextModeChange,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
}: SourcesAndNotesColumnProps) {
  const { t, language } = useTranslation()
  const router = useRouter()
  const [filter, setFilter] = useState<FilterType>('all')

  // Source dialogs
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [addExistingDialogOpen, setAddExistingDialogOpen] = useState(false)
  const [memoryBrowserOpen, setMemoryBrowserOpen] = useState(false)
  const [deleteSourceDialogOpen, setDeleteSourceDialogOpen] = useState(false)
  const [sourceToDelete, setSourceToDelete] = useState<string | null>(null)
  const [removeDialogOpen, setRemoveDialogOpen] = useState(false)
  const [sourceToRemove, setSourceToRemove] = useState<string | null>(null)

  // Note dialogs
  const [showAddNoteDialog, setShowAddNoteDialog] = useState(false)
  const [editingNote, setEditingNote] = useState<NoteResponse | null>(null)
  const [deleteNoteDialogOpen, setDeleteNoteDialogOpen] = useState(false)
  const [noteToDelete, setNoteToDelete] = useState<string | null>(null)

  const { openModal } = useModalManager()
  const { data: memoryHubStatus } = useMemoryHubStatus()
  const deleteSource = useDeleteSource()
  const retrySource = useRetrySource()
  const removeFromNotebook = useRemoveSourceFromNotebook()
  const deleteNote = useDeleteNote()

  // Collapsible
  const { sourcesCollapsed, toggleSources, setSources, setStudio } = useNotebookColumnsStore()
  const collapseButton = useMemo(
    () => createCollapseButton(toggleSources, t.navigation.sources + ' & ' + t.common.notes),
    [toggleSources, t.navigation.sources, t.common.notes]
  )

  // Infinite scroll
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container || !hasNextPage || isFetchingNextPage || !fetchNextPage) return
    const { scrollTop, scrollHeight, clientHeight } = container
    if (scrollHeight - scrollTop - clientHeight < 200) {
      fetchNextPage()
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return
    container.addEventListener('scroll', handleScroll)
    return () => container.removeEventListener('scroll', handleScroll)
  }, [handleScroll])

  // Source handlers
  const handleSourceClick = (sourceId: string) => openModal('source', sourceId)
  const handleDeleteSourceClick = (sourceId: string) => { setSourceToDelete(sourceId); setDeleteSourceDialogOpen(true) }
  const handleDeleteSourceConfirm = async () => {
    if (!sourceToDelete) return
    try { await deleteSource.mutateAsync(sourceToDelete); setDeleteSourceDialogOpen(false); setSourceToDelete(null); onRefreshSources?.() }
    catch (e) { console.error('Failed to delete source:', e) }
  }
  const handleRemoveFromNotebook = (sourceId: string) => { setSourceToRemove(sourceId); setRemoveDialogOpen(true) }
  const handleRemoveConfirm = async () => {
    if (!sourceToRemove) return
    try { await removeFromNotebook.mutateAsync({ notebookId, sourceId: sourceToRemove }); setRemoveDialogOpen(false); setSourceToRemove(null) }
    catch (e) { console.error('Failed to remove source:', e) }
  }
  const handleRetry = async (sourceId: string) => {
    try { await retrySource.mutateAsync(sourceId) }
    catch (e) { console.error('Failed to retry source:', e) }
  }

  // Note handlers
  const handleDeleteNoteClick = (noteId: string) => { setNoteToDelete(noteId); setDeleteNoteDialogOpen(true) }
  const handleDeleteNoteConfirm = async () => {
    if (!noteToDelete) return
    try { await deleteNote.mutateAsync(noteToDelete); setDeleteNoteDialogOpen(false); setNoteToDelete(null) }
    catch (e) { console.error('Failed to delete note:', e) }
  }

  // Filter logic
  const filteredSources = useMemo(() => {
    if (!sources) return []
    if (filter === 'notes') return []
    if (filter === 'sources') return sources.filter(s => !s.asset?.memory_ref)
    if (filter === 'memories') return sources.filter(s => !!s.asset?.memory_ref)
    return sources // 'all'
  }, [sources, filter])

  const filteredNotes = useMemo(() => {
    if (!notes) return []
    if (filter === 'sources' || filter === 'memories') return []
    return notes // 'all' or 'notes'
  }, [notes, filter])

  const totalCount = (sources?.length || 0) + (notes?.length || 0)
  const showSources = filter === 'all' || filter === 'sources' || filter === 'memories'
  const showNotes = filter === 'all' || filter === 'notes'
  const isLoading = (showSources && sourcesLoading) || (showNotes && notesLoading)
  const isEmpty = filteredSources.length === 0 && filteredNotes.length === 0 && !isLoading

  return (
    <>
      <CollapsibleColumn
        isCollapsed={sourcesCollapsed}
        onToggle={toggleSources}
        collapsedIcon={FileText}
        collapsedLabel={t.navigation.sources}
      >
        <Card className="h-full flex flex-col flex-1 overflow-hidden">
          <CardHeader className="pb-2 flex-shrink-0">
            <div className="flex items-center justify-between gap-2">
              {/* Filter dropdown */}
              <div className="flex items-center gap-2">
                <Select value={filter} onValueChange={(v) => setFilter(v as FilterType)}>
                  <SelectTrigger className="h-7 text-[11px] w-auto min-w-[80px] px-2">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{t.common.filterAll}</SelectItem>
                    <SelectItem value="sources">{t.common.filterSources}</SelectItem>
                    <SelectItem value="memories">{t.common.filterMemories}</SelectItem>
                    <SelectItem value="notes">{t.common.filterNotes}</SelectItem>
                  </SelectContent>
                </Select>
                {totalCount > 0 && (
                  <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">{totalCount}</Badge>
                )}
              </div>

              <div className="flex items-center gap-1">
                {/* Unified Add dropdown */}
                <DropdownMenu open={dropdownOpen} onOpenChange={setDropdownOpen}>
                  <DropdownMenuTrigger asChild>
                    <Button size="sm" variant="outline" className="h-6 text-[11px] px-2">
                      <Plus className="h-3 w-3 mr-0.5" />
                      {t.common.create}
                      <ChevronDown className="h-2.5 w-2.5 ml-0.5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => { setDropdownOpen(false); setAddDialogOpen(true) }}>
                      <Plus className="h-4 w-4 mr-2" />
                      {t.sources.addSource}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => { setDropdownOpen(false); router.push(`/sources?from=${notebookId}`) }}>
                      <Link2 className="h-4 w-4 mr-2" />
                      {t.sources.addExistingTitle}
                    </DropdownMenuItem>
                    {memoryHubStatus?.connected && (
                      <DropdownMenuItem onClick={() => { setDropdownOpen(false); router.push(`/sources?tab=memories&from=${notebookId}`) }}>
                        <Brain className="h-4 w-4 mr-2" />
                        {t.memories?.addFromMemory || 'Add from Memory'}
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => { setDropdownOpen(false); setEditingNote(null); setShowAddNoteDialog(true); setSources(false); setStudio(true) }}>
                      <StickyNote className="h-4 w-4 mr-2" />
                      {t.common.writeNote}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                {collapseButton}
              </div>
            </div>
          </CardHeader>

          <CardContent ref={scrollContainerRef} className="flex-1 overflow-y-auto min-h-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <LoadingSpinner />
              </div>
            ) : isEmpty ? (
              <EmptyState
                icon={filter === 'notes' ? StickyNote : FileText}
                title={filter === 'notes' ? t.notebooks.noNotesYet : t.sources.noSourcesYet}
                description={filter === 'notes' ? t.sources.createFirstNote : t.sources.createFirstSource}
              />
            ) : (
              <div className="space-y-3">
                {/* Sources */}
                {filteredSources.map((source) => (
                  <SourceCard
                    key={source.id}
                    source={source}
                    onClick={handleSourceClick}
                    onDelete={handleDeleteSourceClick}
                    onRetry={handleRetry}
                    onRemoveFromNotebook={handleRemoveFromNotebook}
                    onRefresh={onRefreshSources}
                    showRemoveFromNotebook={true}
                    contextMode={sourceContextSelections?.[source.id]}
                    onContextModeChange={onSourceContextModeChange
                      ? (mode) => onSourceContextModeChange(source.id, mode)
                      : undefined
                    }
                  />
                ))}
                {isFetchingNextPage && (
                  <div className="flex items-center justify-center py-4">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                )}

                {/* Notes */}
                {filteredNotes.map((note) => (
                  <div
                    key={note.id}
                    className="p-3 border rounded-lg card-hover group relative cursor-pointer"
                    onClick={() => setEditingNote(note)}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {note.note_type === 'ai' ? (
                          <Bot className="h-4 w-4 text-primary" />
                        ) : (
                          <User className="h-4 w-4 text-muted-foreground" />
                        )}
                        <Badge variant="secondary" className="text-xs">
                          {note.note_type === 'ai' ? t.common.aiGenerated : t.common.human}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                          {formatDistanceToNow(new Date(note.updated), {
                            addSuffix: true,
                            locale: getDateLocale(language)
                          })}
                        </span>
                        {onNoteContextModeChange && noteContextSelections?.[note.id] && (
                          <div onClick={(e) => e.stopPropagation()}>
                            <ContextToggle
                              mode={noteContextSelections[note.id]}
                              hasInsights={false}
                              onChange={(mode) => onNoteContextModeChange(note.id, mode)}
                            />
                          </div>
                        )}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 w-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-48">
                            <DropdownMenuItem
                              onClick={(e) => { e.stopPropagation(); handleDeleteNoteClick(note.id) }}
                              className="text-red-600 focus:text-red-600"
                            >
                              <Trash2 className="h-4 w-4 mr-2" />
                              {t.notebooks.deleteNote}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                    {note.title && (
                      <h4 className="text-sm font-medium mb-2 break-all">{note.title}</h4>
                    )}
                    {note.content && (
                      <p className="text-sm text-muted-foreground line-clamp-3 break-all">
                        {note.content}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </CollapsibleColumn>

      {/* Source Dialogs */}
      <AddSourceDialog open={addDialogOpen} onOpenChange={setAddDialogOpen} defaultNotebookId={notebookId} />
      <AddExistingSourceDialog open={addExistingDialogOpen} onOpenChange={setAddExistingDialogOpen} notebookId={notebookId} onSuccess={onRefreshSources} />
      <MemoryBrowser open={memoryBrowserOpen} onOpenChange={setMemoryBrowserOpen} notebookId={notebookId} />
      <ConfirmDialog open={deleteSourceDialogOpen} onOpenChange={setDeleteSourceDialogOpen} title={t.sources.delete} description={t.sources.deleteConfirm} confirmText={t.common.delete} onConfirm={handleDeleteSourceConfirm} isLoading={deleteSource.isPending} confirmVariant="destructive" />
      <ConfirmDialog open={removeDialogOpen} onOpenChange={setRemoveDialogOpen} title={t.sources.removeFromNotebook} description={t.sources.removeConfirm} confirmText={t.common.remove} onConfirm={handleRemoveConfirm} isLoading={removeFromNotebook.isPending} confirmVariant="default" />

      {/* Note Dialogs */}
      <NoteEditorDialog
        open={showAddNoteDialog || Boolean(editingNote)}
        onOpenChange={(open) => { if (!open) { setShowAddNoteDialog(false); setEditingNote(null) } else { setShowAddNoteDialog(true) } }}
        notebookId={notebookId}
        note={editingNote ?? undefined}
      />
      <ConfirmDialog open={deleteNoteDialogOpen} onOpenChange={setDeleteNoteDialogOpen} title={t.notebooks.deleteNote} description={t.notebooks.deleteNoteConfirm} confirmText={t.common.delete} onConfirm={handleDeleteNoteConfirm} isLoading={deleteNote.isPending} confirmVariant="destructive" />
    </>
  )
}
