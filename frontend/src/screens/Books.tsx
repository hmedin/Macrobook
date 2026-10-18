import { useEffect, useRef, useState } from 'react'
import { supabase } from '../lib'
import { api } from '../lib'
import { deletePdf, getPdf, savePdf, sha256 } from '../localpdf'

const API = import.meta.env.VITE_API_URL as string

export default function Books() {
  const [books, setBooks] = useState<any[]>([])
  const [local, setLocal] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState('')
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const [olderCopies, setOlderCopies] = useState<any[]>([])
  const [updating, setUpdating] = useState<any>(null)
  const updateRef = useRef<HTMLInputElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const reattach = useRef<HTMLInputElement>(null)
  const [reattachFor, setReattachFor] = useState<string | null>(null)

  async function load() {
    const list = await api('/books')
    setBooks(list)
    return list
    const have: Record<string, boolean> = {}
    for (const b of list) have[b.file_hash] = !!(await getPdf(b.file_hash).catch(() => undefined))
    setLocal(have)
  }
  useEffect(() => { load().catch((e) => setErr(e.message)) }, [])

  async function importPdf(file: File, replace?: any) {
    setErr(''); setResult(null)
    setBusy('Uploading and reading your cookbook… this can take a minute for big files.')
    try {
      const { data } = await supabase.auth.getSession()
      const form = new FormData()
      form.append('file', file)
      if (replace) { form.append('replaces', String(replace.id)); form.append('title', replace.title) }
      const res = await fetch(`${API}/api/books/import`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${data.session?.access_token}` },
        body: form,
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Import failed (${res.status})`)
      await savePdf(body.file_hash, file)  // keep the original on this device for side-by-side checks
      setResult(body)
      if (replace && body.replaced && !body.replaced.skipped && !body.replaced.same_file) {
        await deletePdf(replace.file_hash).catch(() => {})  // old edition's local copy is no longer needed
      }
      const list = await load()
      const norm = (t: string) => t.toLowerCase().replace(/[^a-z0-9]/g, '')
      const mine = norm(body.title)
      setOlderCopies(replace ? [] : list.filter((b: any) => {
        const other = norm(b.title)
        return b.id !== body.id && other.length >= 6 && (other === mine || other.includes(mine) || mine.includes(other))
      }))
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy('')
    }
  }

  async function reattachPdf(file: File, hash: string) {
    setErr('')
    if ((await sha256(file)) !== hash) { setErr('That file doesn’t match this cookbook.'); return }
    await savePdf(hash, file)
    load()
  }

  async function remove(b: any, ask = true) {
    if (ask && !confirm(`Remove “${b.title}”? Its recipes will no longer appear in search. Past logs are kept.`)) return
    await api(`/books/${b.id}`, { method: 'DELETE' })
    await deletePdf(b.file_hash).catch(() => {})
    load()
  }

  return (
    <div>
      <header className="top">
        <div>
          <h1>Cookbooks</h1>
          <p className="note">Import a PDF and its recipes show up in search.</p>
        </div>
        <button className="markbtn" disabled={!!busy} onClick={() => fileRef.current?.click()}>＋ <span className="lbl">Import PDF</span></button>
        <input ref={fileRef} type="file" accept="application/pdf" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) importPdf(f); e.target.value = '' }} />
        <input ref={updateRef} type="file" accept="application/pdf" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f && updating) importPdf(f, updating); e.target.value = '' }} />
        <input ref={reattach} type="file" accept="application/pdf" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f && reattachFor) reattachPdf(f, reattachFor); e.target.value = '' }} />
      </header>

      {busy && <p className="card note">{busy}</p>}
      {err && <p className="error">{err}</p>}

      {result && (
        <section className="card">
          <h2>{result.reused ? 'Added to your library' : 'Imported'}: {result.title}</h2>
          <p className="note">
            {result.recipes} recipes{result.reused ? ' (already read for another copy of this book, so nothing new was processed)' : ''}.
          </p>
          {result.replaced?.skipped && (
            <p className="warn">
              This doesn’t look like a new edition of that book (only {result.replaced.overlap_pct}% of the recipes match),
              so it was added as a separate book and your original was kept.
            </p>
          )}
          {result.replaced?.same_file && <p className="note">That’s the same file you already have, so nothing changed.</p>}
          {result.replaced && !result.replaced.skipped && !result.replaced.same_file && (
            <p className="note">
              Updated. {result.replaced.changed_count} recipe(s) have different numbers and need re-checking,
              {' '}{result.replaced.added_count} new, {result.replaced.removed_count} no longer in the book.
              {result.replaced.kept_verified > 0 && ` ${result.replaced.kept_verified} unchanged recipe(s) stayed verified.`}
              {' '}Your saved serving splits were kept.
              {result.replaced.changed?.length > 0 && ` Changed: ${result.replaced.changed.slice(0, 6).join(', ')}${result.replaced.changed_count > 6 ? '…' : ''}.`}
            </p>
          )}
          {result.flagged?.length > 0 && <p className="warn">Double-check these, since their numbers didn’t add up: {result.flagged.join(', ')}</p>}
          {result.read_by_ai > 0 && (
            <p className="note">{result.read_by_ai} recipe(s) were read by AI from pages with a different layout. They’ll get the same page-by-page check when you first log them.</p>
          )}
          {result.estimated > 0 && (
            <p className="warn">⚠ {result.estimated} recipe(s) had no macros printed, so the numbers are estimated from the ingredients. They’re marked as estimates, and can be off by 10–20% or more.</p>
          )}
          {result.ai_error && <p className="note">{result.ai_error}</p>}
          <p className="note">The first time you log each recipe, you’ll see the original page next to what we read, so you can confirm it.</p>
        </section>
      )}

      {olderCopies.length > 0 && (
        <section className="card">
          <h2>Is this a newer edition?</h2>
          <p className="note">
            You already have {olderCopies.map((b) => `“${b.title}”`).join(', ')}. A new edition can have different numbers,
            so you’ll re-check recipes the first time you log them. Remove the old version to avoid duplicates in search?
          </p>
          <div className="row">
            <button onClick={async () => { for (const b of olderCopies) await remove(b, false); setOlderCopies([]) }}>Remove old version</button>
            <button className="ghost" onClick={() => setOlderCopies([])}>Keep both</button>
          </div>
        </section>
      )}

      <section className="card list">
        {books.length === 0 && !busy && <p className="note" style={{ padding: 14 }}>No cookbooks yet. Tap Import PDF to add one.</p>}
        {books.map((b) => (
          <div key={b.id} className="meal">
            <div className="mealhead static">
              <span className="tile">📖</span>
              <span className="mealtext">
                <b>{b.title}</b>
                <small>
                  {b.recipes} recipes ·{' '}
                  {local[b.file_hash] ? 'original pages on this device' : (
                    <button className="link inline" onClick={() => { setReattachFor(b.file_hash); reattach.current?.click() }}>
                      attach PDF for side-by-side checks
                    </button>
                  )}
                </small>
              </span>
              <button className="link" disabled={!!busy} title="Replace this book with a newer edition"
                onClick={() => { setUpdating(b); setTimeout(() => updateRef.current?.click(), 0) }}>Update</button>
              <button className="link" aria-label="Remove cookbook" onClick={() => remove(b)}>✕</button>
            </div>
          </div>
        ))}
      </section>
      <p className="note">Your PDFs are kept only on this device. The server stores just recipe names and nutrition numbers.</p>
    </div>
  )
}
