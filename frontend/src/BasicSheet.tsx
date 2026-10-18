import { useState } from 'react'

type Portion = { unit: string; grams: number }

// Log a basic food (USDA data, macros per 100 g) by weight or by a household portion like "1 large egg".
export default function BasicSheet({ food, slot, onConfirm, onCancel }: {
  food: any
  slot: string
  onConfirm: (servings: number, label: string) => Promise<void>
  onCancel: () => void
}) {
  const portions: Portion[] = Array.isArray(food.portions) ? food.portions : []
  // Start on the first household portion when there is one ("1 large"), otherwise 100 g.
  const [unit, setUnit] = useState<string>(portions.length ? '0' : 'g')
  const [amount, setAmount] = useState(portions.length ? '1' : '100')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const amt = Number(amount) || 0
  const chosen = unit === 'g' ? null : portions[Number(unit)]
  const grams = chosen ? amt * chosen.grams : amt
  const k = grams / 100
  const per = (v: any) => Number(v) * k
  const label = chosen ? `${amt} ${chosen.unit}` : `${Math.round(grams)} g`

  async function go() {
    if (grams <= 0) return
    setBusy(true); setErr('')
    try {
      await onConfirm(k, label)
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
            <p className="note">Adding to {slot} · {Math.round(Number(food.calories))} kcal per 100 g · USDA</p>
          </div>
          <button className="link" onClick={onCancel} aria-label="Close">✕</button>
        </div>

        <div className="amountrow">
          <label>Amount
            <input type="number" min="0" step={unit === 'g' ? 1 : 0.25} inputMode="decimal" value={amount}
              onChange={(e) => setAmount(e.target.value)} />
          </label>
          <label>Unit
            <select value={unit} onChange={(e) => {
              const next = e.target.value
              // Keep a sensible number when switching: 100 for grams, 1 for a portion.
              setAmount(next === 'g' ? '100' : '1'); setUnit(next)
            }}>
              <option value="g">grams</option>
              {portions.map((p, i) => <option key={i} value={String(i)}>{p.unit} ({Math.round(p.grams)} g)</option>)}
            </select>
          </label>
        </div>
        {unit === 'g' && (
          <div className="chips">
            {[50, 100, 150, 200].map((g) => (
              <button key={g} type="button" className={Number(amount) === g ? 'chip on' : 'chip'} onClick={() => setAmount(String(g))}>{g} g</button>
            ))}
          </div>
        )}
        {chosen && <p className="note">{amt} × {chosen.unit} ≈ {Math.round(grams)} g</p>}

        <div className="preview">
          <b>{Math.round(per(food.calories))} kcal</b>
          <span className="note">P {Math.round(per(food.protein_g))}g · C {Math.round(per(food.carbs_g))}g · F {Math.round(per(food.fat_g))}g</span>
        </div>
        <p className="note">Check the name for raw or cooked: the same food has very different calories per gram.</p>
        {err && <p className="error">{err}</p>}
        <button disabled={busy || grams <= 0} onClick={go}>Add to {slot}</button>
      </div>
    </div>
  )
}
