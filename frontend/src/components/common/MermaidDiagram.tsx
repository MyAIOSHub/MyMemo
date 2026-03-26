'use client'

import { useEffect, useRef, useState } from 'react'

interface MermaidDiagramProps {
  code: string
}

export function MermaidDiagram({ code }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string>('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function render() {
      try {
        // Dynamic import to avoid SSR issues
        const mermaid = (await import('mermaid')).default
        mermaid.initialize({
          startOnLoad: false,
          theme: document.documentElement.classList.contains('dark') ? 'dark' : 'default',
          securityLevel: 'loose',
        })

        const { svg: renderedSvg } = await mermaid.render(
          `mermaid-${Date.now()}`,
          code.trim()
        )
        if (!cancelled) {
          setSvg(renderedSvg)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to render diagram')
          setSvg('')
        }
      }
    }

    render()
    return () => { cancelled = true }
  }, [code])

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-destructive">Diagram render error: {error}</p>
        <pre className="text-xs bg-muted p-3 rounded-lg overflow-x-auto whitespace-pre-wrap">{code}</pre>
      </div>
    )
  }

  if (!svg) {
    return <div className="text-xs text-muted-foreground">Rendering diagram...</div>
  }

  return (
    <div
      ref={containerRef}
      className="overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
