import { useState } from 'react'
import { api } from './lib'

const BADGE: Record<string, string> = { official: 'Official source', third_party: 'Third-party source', estimate: 'Estimate' }
const KEYS = ['calories', 'protein_g', 'carbs_g', 'fat_g'] as const

// First-use check for restaurant items: what we found, where, and the exact line it came from.
// A lookup can return several items (a plate, a burger and fries); each is checked and can be left out.
// `lookup` = fresh result from /restaurant/lookup; `cached` = a shared item this user hasn't confirmed yet.
export default function RestaurantModal({ items, mode, lookupId, mealNote, onDone, onCancel }: {
  items: any[]
  mode: 'lookup' | 'cached'
  lookupId?: number
  mealNote?: string
  onDone: (foods: any[]) => void
  onCancel: () => void
}) {
  const [vals, setVals] = useState(() =>
    items.map((it) => Object.fromEntries(KEYS.map((k) => [k, String(Math.round(Number(it[k]) || 0))])) as Record<string, string>),
  )
  const [include, setInclude] = useState(() => items.map(() => true))
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const changed = (i: number) => KEYS.some((k) => Number(vals[i][k]) !== Math.round(Number(items[i][k]) || 0))
  const nums = (i: number) => Object.fromEntries(KEYS.map((k) => [k, Number(vals[i][k]) || 0])) as Record<string, number>
  const chosen = items.map((_, i) => i).filter((i) => include[i])
  const total = chosen.reduce((a, i) => a + (Number(vals[i].calories) || 0), 0)

  async function confirm() {
    if (!chosen.length) return
    setBusy(true); setErr('')
    try {
      if (mode === 'lookup') {
        const { foods } = await api('/restaurant/save', {
          method: 'POST',
          body: JSON.stringify({
            lookup_id: lookupId,
            picks: chosen.map((i) => ({ index: i, edits: changed(i) ? nums(i) : undefined })),
          }),
        })
        onDone(foods)
      } else {
        const foods: any[] = []
        for (const i of chosen) {
          const item = items[i]
          if (changed(i)) {
            const { id } = await api('/foods', {
              method: 'POST',
              body: JSON.stringify({ name: `${item.name} (edited)`, serving_desc: item.serving_desc, ...nums(i) }),
            })
            foods.push({ ...item, id, name: `${item.name} (edited)`, source_type: 'custom', verified: true, ...nums(i) })
          } else {
            await api(`/foods/${item.id}/verify`, { method: 'POST' })
            foods.push({ ...item, verified: true })
          }
        }
        onDone(foods)
      }
    } catch (e: any) {
      setErr(e.message); setBusy(false)
    }
  }

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Check these items">
      <div className="modal sheet wide">
        <div className="modalhead">
          <div>
            <h2>{items.length > 1 ? `Check these ${items.length} items` : items[0].name}</h2>
            <p className="note">
              {items.length > 1 ? 'Review each one. Uncheck anything you didn’t have.' : [items[0].restaurant, items[0].serving_desc].filter(Boolean).join(' · ')}
            </p>
          </div>
          <button className="link" onClick={onCancel} aria-label="Close">✕</button>
        </div>
        {mealNote && <p className="note">{mealNote}</p>}

        {items.map((item, i) => {
          const confidence = item.confidence ?? (item.is_estimate ? 'estimate' : 'official')
          const warnings: string[] = []
          if (item.consistent === false) warnings.push('The calories don’t match the macros, so one of them may be wrong.')
          if (mode === 'lookup' && item.quote_matches === false) warnings.push('The quoted text doesn’t show the calorie number. Check the source link.')
          if (confidence === 'estimate') warnings.push('This is an estimate, not an official number.')
          if (confidence === 'third_party') warnings.push('This came from a third-party site, not the restaurant itself. Many restaurants block automated access to their own pages, so we often can’t read them.')
          const note = item.notes || item.estimate_note
          return (
            <section key={i} className={include[i] ? 'itemcard' : 'itemcard off'}>
              <div className="itemhead">
                {items.length > 1 && (
                  <input type="checkbox" checked={include[i]} aria-label={`Include ${item.name}`}
                    onChange={(e) => setInclude(include.map((v, j) => (j === i ? e.target.checked : v)))} />
                )}
                <div>
                  <b>{item.name}</b>
                  <p className="note">{[item.restaurant, item.serving_desc].filter(Boolean).join(' · ')}</p>
                </div>
                <span className={`badge ${confidence}`}>{BADGE[confidence]}</span>
              </div>

              {include[i] && (
                <>
                  <div className="fields">
                    {KEYS.map((k) => (
                      <label key={k}>{k === 'calories' ? 'Calories' : k === 'protein_g' ? 'Protein g' : k === 'carbs_g' ? 'Carbs g' : 'Fat g'}
                        <input type="number" value={vals[i][k]}
                          onChange={(e) => setVals(vals.map((v, j) => (j === i ? { ...v, [k]: e.target.value } : v)))} />
                      </label>
                    ))}
                  </div>

                  {item.assumptions?.length > 0 && (
                    <div className="assume">
                      <b>What we assumed</b>
                      <ul>{item.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul>
                    </div>
                  )}
                  {item.other_values?.length > 0 && (
                    <div className="others">
                      <b>Other sources list</b>
                      <div className="chips wrap">
                        {item.other_values.map((o: any, j: number) => (
                          <span key={j} className="chip static" title={o.source}>{Math.round(o.calories)} kcal · {o.source || 'other site'}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {item.source_quote && <blockquote className="quote">“{item.source_quote}”</blockquote>}
                  {item.source_url && (
                    <a className="srclink" href={item.source_url} target="_blank" rel="noreferrer noopener">Open the source page ↗</a>
                  )}
                  {confidence !== 'official' && (
                    <a className="srclink" target="_blank" rel="noreferrer noopener"
                      href={item.official_url || `https://www.google.com/search?q=${encodeURIComponent(`${item.restaurant ?? ''} ${item.name} nutrition information official`)}`}>
                      {item.official_url ? 'Open the restaurant’s own nutrition page ↗' : 'Check the restaurant’s official numbers ↗'}
                    </a>
                  )}
                  {note && <p className="note">{note}</p>}
                  {warnings.map((w) => <p key={w} className="warn">⚠ {w}</p>)}
                  {changed(i) && <p className="warn">You changed these numbers. They’ll be saved as your own copy, not shared.</p>}
                </>
              )}
            </section>
          )
        })}

        {chosen.length > 1 && <p className="preview"><b>{Math.round(total)} kcal</b><span className="note">for the {chosen.length} items together</span></p>}
        {err && <p className="error">{err}</p>}
        <button disabled={busy || !chosen.length} onClick={confirm}>
          {chosen.length > 1 ? `Looks right, continue with ${chosen.length}` : 'Looks right, continue'}
        </button>
        <button className="link" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}
