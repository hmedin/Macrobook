// Cookbook storage on THIS device only (IndexedDB). Nothing here is uploaded.
//
// Instead of keeping whole PDFs (50-90 MB), we keep one small compressed image per recipe page, which is all the
// side-by-side check needs. Old whole-PDF copies ('pdfs') are converted automatically and then removed.
import pdfjs from './pdf'

const DB = 'cookbooks'
const PDFS = 'pdfs'    // legacy: whole files
const PAGES = 'pages'  // `${hash}:${page}` -> JPEG blob, and `meta:${hash}` -> { pages, bytes }

const PAGE_WIDTH = 800
const JPEG_QUALITY = 0.6

let dbPromise: Promise<IDBDatabase> | null = null

// One shared connection (opening a new one per call would pile up while saving many pages).
function open(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB, 2)
      req.onupgradeneeded = () => {
        const db = req.result
        if (!db.objectStoreNames.contains(PDFS)) db.createObjectStore(PDFS)
        if (!db.objectStoreNames.contains(PAGES)) db.createObjectStore(PAGES)
      }
      req.onsuccess = () => {
        req.result.onversionchange = () => { req.result.close(); dbPromise = null }
        resolve(req.result)
      }
      req.onerror = () => { dbPromise = null; reject(req.error) }
    })
  }
  return dbPromise
}

async function tx<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open()
  return new Promise((resolve, reject) => {
    const req = fn(db.transaction(store, mode).objectStore(store))
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

// ---- legacy whole-PDF copies ----
export const getPdf = (hash: string) => tx<Blob | undefined>(PDFS, 'readonly', (s) => s.get(hash))
export const deletePdf = (hash: string) => tx(PDFS, 'readwrite', (s) => s.delete(hash)).then(() => {})

export async function sha256(blob: Blob): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

// ---- recipe page images ----
export type PagesInfo = { pages: number; bytes: number }

export const pagesInfo = (hash: string) => tx<PagesInfo | undefined>(PAGES, 'readonly', (s) => s.get(`meta:${hash}`))
export const getPageImage = (hash: string, page: number) => tx<Blob | undefined>(PAGES, 'readonly', (s) => s.get(`${hash}:${page}`))

export async function deletePages(hash: string) {
  const db = await open()
  await new Promise<void>((resolve, reject) => {
    const t = db.transaction(PAGES, 'readwrite')
    const store = t.objectStore(PAGES)
    store.delete(`meta:${hash}`)
    store.delete(IDBKeyRange.bound(`${hash}:`, `${hash};`))  // every `${hash}:<page>` key
    t.oncomplete = () => resolve()
    t.onerror = () => reject(t.error)
  })
}

async function putPage(hash: string, page: number, blob: Blob) {
  await tx(PAGES, 'readwrite', (s) => s.put(blob, `${hash}:${page}`))
}

// Renders just the given pages (0-based) of a PDF to small JPEGs and saves them. The PDF itself is not kept.
export async function cachePages(
  file: Blob, hash: string, pages: number[], onProgress?: (done: number, total: number) => void,
): Promise<PagesInfo> {
  await deletePages(hash)
  const task = pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) })
  const doc = await task.promise
  let bytes = 0, done = 0
  try {
    for (const p of pages) {
      if (p < 0 || p >= doc.numPages) { done++; continue }
      const page = await doc.getPage(p + 1)
      const base = page.getViewport({ scale: 1 })
      const viewport = page.getViewport({ scale: PAGE_WIDTH / base.width })
      const canvas = document.createElement('canvas')
      canvas.width = Math.round(viewport.width)
      canvas.height = Math.round(viewport.height)
      const ctx = canvas.getContext('2d')!
      ctx.fillStyle = '#fff'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      await page.render({ canvas, canvasContext: ctx, viewport }).promise
      const blob: Blob | null = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', JPEG_QUALITY))
      page.cleanup()
      if (blob) { await putPage(hash, p, blob); bytes += blob.size }
      onProgress?.(++done, pages.length)
    }
  } finally {
    await task.destroy()
  }
  const info = { pages: pages.length, bytes }
  await tx(PAGES, 'readwrite', (s) => s.put(info, `meta:${hash}`))
  return info
}

export async function deleteAllPdfs() {
  if (dbPromise) { (await dbPromise.catch(() => null))?.close(); dbPromise = null }
  await new Promise<void>((resolve, reject) => {
    const req = indexedDB.deleteDatabase(DB)
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
    req.onblocked = () => resolve()
  })
}
