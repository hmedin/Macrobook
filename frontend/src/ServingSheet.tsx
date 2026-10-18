import { useState } from 'react'
import { api } from './lib'

// Macros for one portion, given how many portions the recipe is split into.
// Mirrors backend/app/services/servings.py.
export function perPortion(food: any, nUser: number | null) {
  const m = {
    calories: Number(food.calories), protein_g: Number(food.protein_g),
    carbs_g: Number(food.carbs_g), fat_g: Number(food.fat_g),
  }
  if (food.is_batch) {
    if (!nUser) return null
    return { calories: m.calories / nUser, protein_g: m.protein_g / nUser, carbs_g: m.carbs_g / nUser, fat_g: m.fat_g / nUser }
  }
  const bs = food.book_servings ? Number(food.book_servings) : null
  if (bs && nUser && nUser !== bs) {
    const k = bs / nUser
    return { calories: m.calories * k, protein_g: m.protein_g * k, carbs_g: m.carbs_g * k, fat_g: m.fat_g * k }
  }
  return m
}

const AMOUNTS = [0.5, 1, 1.5, 2]
const SHARES: [number, number, string][] = [
  [1, 1, 'All'], [1, 2, '½'], [1, 3, '⅓'], [1, 4, '¼'], [1, 6, '⅙'], [1, 8, '⅛'], [1, 12, '1/12'],
]

export default function ServingSheet({ food, slot, onConfirm, onCancel }: {
  food: any
  slot: string
  onConfirm: (amount: number, split: number | null, remember: boolean) => Promise<void>
  onCancel: () => void
}) {
  const splittable = food.source_type === 'recipe' || food.is_batch || !!food.book_servings
  const bookN = food.book_servings ? Number(food.book_servings) : null
  // Total of the whole recipe, so a share can be taken of it.
  const hasTotal = food.is_batch || !!bookN
  const total = hasTotal
    ? {
        calories: Number(food.calories) * (food.is_batch ? 1 : bookN!),
        protein_g: Number(food.protein_g) * (food.is_batch ? 1 : bookN!),
        carbs_g: Number(food.carbs_g) * (food.is_batch ? 1 : bookN!),
        fat_g: Number(food.fat_g) * (food.is_batch ? 1 : bookN!),
      }
    : null

  const initial = food.user_servings ?? (food.is_batch ? '' : food.book_servings ?? '')
  const [mode, setMode] = useState<'share' | 'servings'>(food.is_batch && !food.user_servings ? 'share' : 'servings')
  const [amount, setAmount] = useState('1')
  const [split, setSplit] = useState(String(initial))
  const [num, setNum] = useState('1')
  const [den, setDen] = useState('6')
  const [remember, setRemember] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const [totalW, setTotalW] = useState(food.user_total_weight_g ? String(Math.round(food.user_total_weight_g)) : '')
  const [grams, setGrams] = useState('')
  const [editW, setEditW] = useState(false)
  const [wDraft, setWDraft] = useState('')

  async function saveWeight() {
    const w = Number(wDraft)
    if (!w || w <= 0) return
    try {
      await api(`/foods/${food.id}/weight`, { method: 'PUT', body: JSON.stringify({ total_weight_g: w }) })
      setTotalW(String(Math.round(w))); setEditW(false); setErr('')
    } catch (e: any) {
      setErr(e.message)
    }
  }

  const byGrams = Number(grams) > 0 && Number(totalW) > 0
  const share = byGrams
    ? Number(grams) / Number(totalW)
    : Number(num) > 0 && Number(den) > 0 ? Number(num) / Number(den) : 0
  const n = Number(split) || null
  const amt = Number(amount) || 0
  const port = perPortion(food, splittable ? n : null)
  const unit =
    mode === 'share'
      ? total && share > 0 && share <= 1
        ? { c: total.calories * share, p: total.protein_g * share, cb: total.carbs_g * share, f: total.fat_g * share }
        : null
      : port
        ? { c: port.calories * amt, p: port.protein_g * amt, cb: port.carbs_g * amt, f: port.fat_g * amt }
        : null
  const changed = mode === 'servings' && splittable && n !== null && n !== (food.user_servings ?? food.book_servings ?? null)
  const valid = !!unit && (mode === 'share' ? share > 0 : amt > 0)

  async function go() {
    if (!valid) return
    setBusy(true); setErr('')
    try {
      if (mode === 'share') {
        // Batch: whole batch is 1 portion. Per-serving: use the book's N so portion = per-serving macros.
        if (food.is_batch) await onConfirm(share, 1, false)
        else await onConfirm(share * bookN!, bookN, false)
      } else {
        await onConfirm(amt, splittable ? n : null, remember && changed)
      }
    } catch (e: any) {
      setErr(e.message); setBusy(false)
    }
  }

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="How much did you have?">
      <div className="modal sheet">
        <div className="modalhead">
          <div>
            <h2>{food.name}</h2>
            <p className="note">Adding to {slot}{food.serving_desc ? ` · ${food.serving_desc}` : ''}</p>
          </div>
          <button className="link" onClick={onCancel} aria-label="Close">✕</button>
        </div>

        {hasTotal && (
          <div className="seg" role="tablist">
            <button type="button" className={mode === 'share' ? 'on' : ''} onClick={() => setMode('share')}>Share of the recipe</button>
            <button type="button" className={mode === 'servings' ? 'on' : ''} onClick={() => setMode('servings')}>Servings</button>
          </div>
        )}

        {mode === 'share' ? (
          <div>
            <p className="note">About how much of the whole recipe did you eat?</p>
            <div className="chips wrap">
              {SHARES.map(([a, b, label]) => (
                <button key={label} type="button" className={Number(num) === a && Number(den) === b ? 'chip on' : 'chip'}
                  onClick={() => { setNum(String(a)); setDen(String(b)) }}>{label}</button>
              ))}
            </div>
            <div className="fraction">
              <input type="number" min="1" inputMode="numeric" value={num} onChange={(e) => setNum(e.target.value)} aria-label="Parts eaten" />
              <span>/</span>
              <input type="number" min="1" inputMode="numeric" value={den} onChange={(e) => setDen(e.target.value)} aria-label="Parts in the whole" />
              <span className="note">of the whole recipe</span>
            </div>
            {share > 1 && <p className="error">That’s more than the whole recipe.</p>}
            {Number(totalW) > 0 && !editW ? (
              <div className="gramsbox">
                <label>Or enter grams you ate
                  <input type="number" min="1" inputMode="decimal" placeholder="e.g. 350" value={grams} onChange={(e) => setGrams(e.target.value)} />
                </label>
                <p className="note">Based on your saved total of {totalW} g.{' '}
                  <button type="button" className="link inline" onClick={() => { setWDraft(totalW); setEditW(true) }}>Change</button>
                </p>
              </div>
            ) : editW ? (
              <div className="gramsbox">
                <label>Total weight of the finished dish (g)
                  <input type="number" min="1" inputMode="decimal" placeholder="e.g. 3800" value={wDraft} onChange={(e) => setWDraft(e.target.value)} />
                </label>
                <p className="note">Weigh the full pot or pan and subtract the empty container. It’s saved for this recipe on your account.</p>
                <div className="row">
                  <button type="button" onClick={saveWeight}>Save weight</button>
                  <button type="button" className="link" onClick={() => setEditW(false)}>Cancel</button>
                </div>
              </div>
            ) : (
              <button type="button" className="link" onClick={() => setEditW(true)}>＋ Add total weight to log by grams</button>
            )}
          </div>
        ) : (
          <>
            {splittable && (
              <div className="splitbox">
                <label>
                  {food.is_batch ? 'This is a whole batch. How many servings does it make?' : 'This recipe makes how many servings?'}
                  <input type="number" min="1" step="1" inputMode="numeric" placeholder="e.g. 8" value={split}
                    onChange={(e) => setSplit(e.target.value)} />
                </label>
                {!food.is_batch && bookN && n && n !== bookN && (
                  <p className="note">The book says it makes {bookN}. Numbers are rescaled to your split.</p>
                )}
                {changed && (
                  <label className="row"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
                    Remember this split for this recipe</label>
                )}
              </div>
            )}
            <div>
              <label>How many servings did you have?
                <input type="number" min="0" step="0.25" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
              </label>
              <div className="chips">
                {AMOUNTS.map((a) => (
                  <button key={a} type="button" className={Number(amount) === a ? 'chip on' : 'chip'} onClick={() => setAmount(String(a))}>
                    {a === 0.5 ? '½' : a === 1.5 ? '1½' : a}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        <div className="preview">
          {unit ? (
            <>
              <b>{Math.round(unit.c)} kcal</b>
              <span className="note">P {Math.round(unit.p)}g · C {Math.round(unit.cb)}g · F {Math.round(unit.f)}g</span>
            </>
          ) : (
            <span className="note">{mode === 'share' ? 'Pick how much you had.' : 'Enter how many servings this makes to see the numbers.'}</span>
          )}
        </div>
        {food.is_estimate && <p className="warn">⚠ Estimated numbers, not exact.</p>}
        {err && <p className="error">{err}</p>}
        <button disabled={busy || !valid} onClick={go}>Add to {slot}</button>
      </div>
    </div>
  )
}
