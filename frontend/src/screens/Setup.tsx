import { useState, type ReactNode } from 'react'
import { api, cmToIn, inToCm, kgToLb, lbToKg, today } from '../lib'

const LEVELS = [
  { v: 'sedentary', l: 'Sedentary: desk job, little daily movement' },
  { v: 'light', l: 'Light: some walking or on your feet part of the day' },
  { v: 'moderate', l: 'Moderate: on your feet most of the day' },
  { v: 'high', l: 'High: physical job' },
  { v: 'extreme', l: 'Extreme: very physical job all day' },
]

// Rate presets in lb/week (converted for metric users on display).
const RATES = [
  { lb: -2, l: 'Aggressive loss (-2 lb/wk)' },
  { lb: -1, l: 'Moderate loss (-1 lb/wk)' },
  { lb: -0.5, l: 'Gentle loss (-0.5 lb/wk)' },
  { lb: 0, l: 'Maintain' },
  { lb: 0.5, l: 'Gentle gain (+0.5 lb/wk)' },
  { lb: 1, l: 'Moderate gain (+1 lb/wk)' },
]

function recommend(job: string, days: number, hard: boolean): string {
  // Activity level reflects daily life; workouts are logged separately.
  if (job === 'physical') return 'high'
  if (job === 'feet') return 'moderate'
  if (job === 'mixed') return 'light'
  return days >= 6 && hard ? 'light' : 'sedentary'
}

export default function Setup({ existing, onDone, children }: { existing?: any; onDone: () => void; children?: ReactNode }) {
  const [unit, setUnit] = useState<'imperial' | 'metric'>(existing?.unit_pref ?? 'imperial')
  const [sex, setSex] = useState(existing?.sex ?? 'male')
  const [birthdate, setBirthdate] = useState(existing?.birthdate ?? '')
  const imp = unit === 'imperial'
  const [height, setHeight] = useState(
    existing ? String(Math.round(imp ? cmToIn(existing.height_cm) : existing.height_cm)) : '',
  )
  const [weight, setWeight] = useState('')
  const [level, setLevel] = useState(existing?.activity_level ?? 'sedentary')
  const [rateLb, setRateLb] = useState(
    existing ? Math.round(kgToLb(Number(existing.goal_rate_kg_per_week)) * 2) / 2 : -0.5,
  )
  const [eatBack, setEatBack] = useState(existing?.exercise_eat_back ?? 'none')
  const [job, setJob] = useState('desk')
  const [days, setDays] = useState(3)
  const [hard, setHard] = useState(false)
  const [suggested, setSuggested] = useState('')
  const [err, setErr] = useState('')

  // Convert what's already typed so switching units doesn't silently change the value.
  function changeUnit(next: 'imperial' | 'metric') {
    if (next === unit) return
    const h = Number(height), w = Number(weight)
    if (h) setHeight(String(Math.round(next === 'metric' ? inToCm(h) : cmToIn(h))))
    if (w) setWeight((next === 'metric' ? lbToKg(w) : kgToLb(w)).toFixed(1))
    setUnit(next)
  }

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    try {
      await api('/profile', {
        method: 'PUT',
        body: JSON.stringify({
          sex, birthdate,
          height_cm: imp ? inToCm(Number(height)) : Number(height),
          activity_level: level, unit_pref: unit,
          goal_rate_kg_per_week: lbToKg(rateLb),
          exercise_eat_back: eatBack,
        }),
      })
      if (weight) {
        await api('/weights', {
          method: 'PUT',
          body: JSON.stringify({ date: today(), weight_kg: imp ? lbToKg(Number(weight)) : Number(weight) }),
        })
      }
      onDone()
    } catch (e: any) {
      setErr(e.message)
    }
  }

  return (
    <form className="card narrow profile" onSubmit={save}>
      <h1>{existing ? 'Profile & goals' : 'Set up your goals'}</h1>
      <label>Units
        <select value={unit} onChange={(e) => changeUnit(e.target.value as 'imperial' | 'metric')}>
          <option value="imperial">Imperial (lb, in)</option>
          <option value="metric">Metric (kg, cm)</option>
        </select>
      </label>
      <label>Sex (used in the calorie formula)
        <select value={sex} onChange={(e) => setSex(e.target.value)}>
          <option value="male">Male</option><option value="female">Female</option>
        </select>
      </label>
      <label>Birthdate
        <input type="date" value={birthdate} onChange={(e) => setBirthdate(e.target.value)} required />
      </label>
      <label>Height ({imp ? 'inches' : 'cm'})
        <input type="number" value={height} onChange={(e) => setHeight(e.target.value)} required />
      </label>
      <label>{existing ? 'Log today’s weight' : 'Current weight'} ({imp ? 'lb' : 'kg'})
        <input type="number" step="0.1" value={weight} onChange={(e) => setWeight(e.target.value)} required={!existing} />
      </label>

      <label>Daily activity level
        <select value={level} onChange={(e) => setLevel(e.target.value)}>
          {LEVELS.map((x) => <option key={x.v} value={x.v}>{x.l}</option>)}
        </select>
      </label>
      <details>
        <summary>Not sure? Answer a few questions</summary>
        <label>Your typical day
          <select value={job} onChange={(e) => setJob(e.target.value)}>
            <option value="desk">Mostly sitting (office, studying)</option>
            <option value="mixed">Mix of sitting and walking</option>
            <option value="feet">On my feet most of the day</option>
            <option value="physical">Physical labor</option>
          </select>
        </label>
        <label>Workouts per week
          <input type="number" min={0} max={14} value={days} onChange={(e) => setDays(Number(e.target.value))} />
        </label>
        <label className="row"><input type="checkbox" checked={hard} onChange={(e) => setHard(e.target.checked)} />
          Workouts are hard (running, intense training)</label>
        <button type="button" onClick={() => { const l = recommend(job, days, hard); setLevel(l); setSuggested(l) }}>Suggest a level</button>
        {suggested && <p className="note">Suggested: <b>{LEVELS.find((x) => x.v === suggested)?.l}</b>. It’s selected above; change it if it doesn’t fit.</p>}
        <p className="note">Pick the level for your daily life only. Log runs and workouts separately so they aren’t counted twice.</p>
      </details>

      <label>Goal
        <select value={rateLb} onChange={(e) => setRateLb(Number(e.target.value))}>
          {RATES.map((r) => <option key={r.lb} value={r.lb}>{r.l}</option>)}
        </select>
      </label>
      <label>Eat back exercise calories?
        <select value={eatBack} onChange={(e) => setEatBack(e.target.value)}>
          <option value="none">No</option><option value="half">Half</option><option value="all">All</option>
        </select>
      </label>
      <button type="submit">Save</button>
      {err && <p className="error">{err}</p>}
      {children}
    </form>
  )
}
