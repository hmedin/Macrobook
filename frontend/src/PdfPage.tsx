import { useEffect, useRef, useState } from 'react'
import pdfjs from './pdf'

// Renders one page (0-based) of a PDF blob onto a canvas.
export default function PdfPage({ blob, page }: { blob: Blob; page: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let cancelled = false
    let task: ReturnType<typeof pdfjs.getDocument> | null = null
    ;(async () => {
      try {
        task = pdfjs.getDocument({ data: new Uint8Array(await blob.arrayBuffer()) })
        const doc = await task.promise
        const p = await doc.getPage(page + 1)
        if (cancelled || !ref.current) return
        const viewport = p.getViewport({ scale: 1.6 })
        const canvas = ref.current
        canvas.width = viewport.width
        canvas.height = viewport.height
        await p.render({ canvas, canvasContext: canvas.getContext('2d')!, viewport }).promise
      } catch (e: any) {
        if (!cancelled) setErr('Could not display the page')
      }
    })()
    return () => { cancelled = true; task?.destroy() }
  }, [blob, page])

  return err ? <p className="error">{err}</p> : <canvas ref={ref} className="pdfpage" />
}
