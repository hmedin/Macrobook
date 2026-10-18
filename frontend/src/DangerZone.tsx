import { useState } from 'react'
import { api, supabase } from './lib'
import { deleteAllPdfs } from './localpdf'

export function LegalLinks() {
  return (
    <p className="note legal">
      <a href="/privacy.html" target="_blank" rel="noopener noreferrer">Privacy policy</a>
      {' · '}Basic food data: USDA FoodData Central
    </p>
  )
}

// Permanently deletes the account and everything tied to it. Requires typing DELETE.
export default function DangerZone() {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function remove() {
    setBusy(true); setErr('')
    try {
      await api('/account', { method: 'DELETE', body: JSON.stringify({ confirm: text }) })
      await deleteAllPdfs().catch(() => {})  // the app's hidden browser copies, never the user's own files
      try { localStorage.clear() } catch { /* private mode */ }
      await supabase.auth.signOut({ scope: 'local' })
      window.location.href = '/'
    } catch (e: any) {
      setErr(e.message); setBusy(false)
    }
  }

  return (
    <section className="card narrow goalcard">
      <details>
        <summary className="dangersum">Delete my account and data</summary>
        <p className="note">
          This permanently deletes your profile, weights, food and exercise logs, foods you added, goal history,
          and your imported cookbook data from our servers, and clears the cookbook copies the app saved in this browser.
          It can’t be undone. The original PDF files you imported are never touched.
        </p>
        <label>Type <b>DELETE</b> to confirm
          <input value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" />
        </label>
        <button className="dangerbtn" disabled={busy || text !== 'DELETE'} onClick={remove}>
          {busy ? 'Deleting…' : 'Permanently delete everything'}
        </button>
        {err && <p className="error">{err}</p>}
      </details>
    </section>
  )
}
