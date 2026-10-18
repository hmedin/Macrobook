// Cookbook PDFs stay on this device (IndexedDB). They are never stored on the server.
const DB = 'cookbooks'
const STORE = 'pdfs'

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open()
  return new Promise((resolve, reject) => {
    const req = fn(db.transaction(STORE, mode).objectStore(STORE))
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export const savePdf = (hash: string, blob: Blob) => tx('readwrite', (s) => s.put(blob, hash)).then(() => {})
export const getPdf = (hash: string) => tx<Blob | undefined>('readonly', (s) => s.get(hash))
export const deletePdf = (hash: string) => tx('readwrite', (s) => s.delete(hash)).then(() => {})

export async function sha256(blob: Blob): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

export const deleteAllPdfs = () =>
  new Promise<void>((resolve, reject) => {
    const req = indexedDB.deleteDatabase(DB)
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
    req.onblocked = () => resolve()
  })
