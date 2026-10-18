import { useState } from 'react'
import { api } from './lib'

const BADGE: Record<string, string> = { official: 'Official source', third_party: 'Third-party source', estimate: 'Estimate' }

// First-use check for a restaurant item: what we found, where, and the exact line it came from.
// `lookup` = fresh result from /restaurant/lookup; `cached` = an existing shared item not yet confirmed by this user.
export default function RestaurantModal({ item, mode, onDone, onCancel }: {
  item: any
  mode: 'lookup' | 'cached'
  onDone: (food: any) => void
  onCancel: () => void
}) {
  const [v, setV] = useState({
    calories: String(Math.round(item.calories)), protein_g: String(Math.round(item.protein_g)),
    carbs_g: String(Math.round(item.carbs_g)), fat_g: String(Math.round(item.fat_g)),
  })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const changed =
    Number(v.calories) !== Math.round(item.calories) || Number(v.protein_g) !== Math.round(item.protein_g) ||
    Number(v.carbs_g) !== Math.round(item.carbs_g) || Number(v.fat_g) !== Math.round(item.fat_g)

  const confidence = item.confidence ?? (item.is_estimate ? 'estimate' : 'official')
  const warnings: string[] = []
  if (item.consistent === false) warnings.push('The calories don’t match the macros, so one of them may be wrong.')
  if (mode === 'lookup' && item.quote_matches === false) warnings.push('The quoted text doesn’t show the calorie number. Check the source link.')
  if (confidence === 'estimate') warnings.push('This is an estimate, not an official number.')
  if (confidence === 'third_party') warnings.push('This came from a third-party site, not the restaurant itself.')

  const nums = { calories: Number(v.calories) || 0, protein_g: Number(v.protein_g) || 0, carbs_g: Number(v.carbs_g) || 0, fat_g: Number(v.fat_g) || 0 }

  async function confirm() {
    setBusy(true); setErr('')
    try {
      if (mode === 'lookup') {
        const food = await api('/restaurant/save', {
          method: 'POST',
          body: JSON.stringify({ lookup_id: item.lookup_id, edits: changed ? nums : undefined }),
        })
        onDone(food)
      } else if (changed) {
        const { id } = await api('/foods', {
          method: 'POST',
          body: JSON.stringify({ name: `${item.name} (edited)`, serving_desc: item.serving_desc, ...nums }),
        })
        onDone({ ...item, id, name: `${item.name} (edited)`, source_type: 'custom', verified: true, ...nums })
      } else {
        await api(`/foods/${item.id}/verify`, { method: 'POST' })
        onDone({ ...item, verified: true })
      }
    } catch (e: any) {
      setErr(e.message); setBusy(false)
    }
  }

  const field = (k: keyof typeof v, label: string) => (
    <label>{label}<input type="number" value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} /></label>
  )

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Check this item">
      <div className="modal sheet">
        <div className="modalhead">
          <div>
            <h2>{item.name}</h2>
            <p className="note">{[item.restaurant, item.serving_desc].filter(Boolean).join(' · ')}</p>
          </div>
          <button className="link" onClick={onCancel} aria-label="Close">✕</button>
        </div>

        <span className={`badge ${confidence}`}>{BADGE[confidence]}</span>

        <div className="fields">
          {field('calories', 'Calories')}
          {field('protein_g', 'Protein g')}
          {field('carbs_g', 'Carbs g')}
          {field('fat_g', 'Fat g')}
        </div>

        {item.source_quote && (
          <blockquote className="quote">“{item.source_quote}”</blockquote>
        )}
        {item.source_url && (
          <a className="srclink" href={item.source_url} target="_blank" rel="noreferrer noopener">Open the source page ↗</a>
        )}
        {(item.notes || item.estimate_note) && <p className="note">{item.notes || item.estimate_note}</p>}

        {warnings.map((w) => <p key={w} className="warn">⚠ {w}</p>)}
        {changed && <p className="warn">You changed the numbers. They’ll be saved as your own copy, not shared.</p>}
        {err && <p className="error">{err}</p>}
        <button disabled={busy} onClick={confirm}>{changed ? 'Save my version & continue' : 'Looks right, continue'}</button>
        <button className="link" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}
