import { useState } from 'react'

// Log several confirmed items together (a plate, a burger and fries). Each gets its own number of servings.
export default function MealSheet({ foods, slot, onConfirm, onCancel }: {
  foods: any[]
  slot: string
  onConfirm: (amounts: number[]) => Promise<void>
  onCancel: () => void
}) {
  const [amounts, setAmounts] = useState(() => foods.map(() => '1'))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const amt = (i: number) => Math.max(0, Number(amounts[i]) || 0)
  const total = foods.reduce((a, f, i) => a + Number(f.calories) * amt(i), 0)
  const protein = foods.reduce((a, f, i) => a + Number(f.protein_g) * amt(i), 0)
  const carbs = foods.reduce((a, f, i) => a + Number(f.carbs_g) * amt(i), 0)
  const fat = foods.reduce((a, f, i) => a + Number(f.fat_g) * amt(i), 0)

  async function go() {
    setBusy(true); setErr('')
    try {
      await onConfirm(foods.map((_, i) => amt(i)))
    } catch (e: any) {
      setErr(e.message); setBusy(false)
    }
  }

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Add these items">
      <div className="modal sheet">
        <div className="modalhead">
          <div>
            <h2>Add to {slot}</h2>
            <p className="note">How many servings of each did you have?</p>
          </div>
          <button className="link" onClick={onCancel} aria-label="Close">✕</button>
        </div>

        {foods.map((f, i) => (
          <div key={f.id} className="mealrow">
            <div>
              <b>{f.name}</b>
              <p className="note">{f.serving_desc} · {Math.round(Number(f.calories) * amt(i))} kcal</p>
            </div>
            <input type="number" min="0" step="0.25" inputMode="decimal" value={amounts[i]} aria-label={`Servings of ${f.name}`}
              onChange={(e) => setAmounts(amounts.map((v, j) => (j === i ? e.target.value : v)))} />
          </div>
        ))}

        <div className="preview">
          <b>{Math.round(total)} kcal</b>
          <span className="note">P {Math.round(protein)}g · C {Math.round(carbs)}g · F {Math.round(fat)}g</span>
        </div>
        {err && <p className="error">{err}</p>}
        <button disabled={busy || total <= 0} onClick={go}>Add all to {slot}</button>
      </div>
    </div>
  )
}
