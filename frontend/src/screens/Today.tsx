import { useCallback, useEffect, useRef, useState } from 'react'
import { api, today } from '../lib'
import { MacroBar, Ring } from '../components'
import VerifyModal from '../VerifyModal'
import ServingSheet from '../ServingSheet'
import InstallHelp from '../InstallHelp'
import RestaurantModal from '../RestaurantModal'
import MealSheet from '../MealSheet'

const SLOTS = ['breakfast', 'lunch', 'dinner', 'snack'] as const
type Slot = (typeof SLOTS)[number]
const EMOJI: Record<string, string> = { breakfast: '🍳', lunch: '🥗', dinner: '🍽️', snack: '🍎', exercise: '🏃' }
const EMPTY_HINT: Record<Slot, string> = {
  breakfast: 'Start your day', lunch: 'Add your meal', dinner: 'Plan your evening', snack: 'Anything in between',
}
const KINDS = ['run', 'walk', 'cycle', 'swim', 'strength', 'hiit', 'other'] as const
const DISTANCE_KINDS = ['run', 'walk']

function defaultSlot(): Slot {
  const h = new Date().getHours()
  return h < 11 ? 'breakfast' : h < 15 ? 'lunch' : h < 21 ? 'dinner' : 'snack'
}

function longDate(iso: string) {
  return new Date(iso + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
}

export default function Today({ profile }: { profile: any }) {
  const imp = profile.unit_pref === 'imperial'
  const [day, setDay] = useState(today())
  const [data, setData] = useState<any>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [manual, setManual] = useState(false)
  const [m, setM] = useState({ name: '', calories: '', protein_g: '', carbs_g: '', fat_g: '', save: true })
  const [ex, setEx] = useState({ type: 'run', distance: '', minutes: '', kcal: '' })
  const [done, setDone] = useState(false)
  const [verify, setVerify] = useState<{ slot: Slot; food: any } | null>(null)
  const [pick, setPick] = useState<{ slot: Slot; food: any } | null>(null)
  const [rcheck, setRcheck] = useState<{ slot: Slot; items: any[]; mode: 'lookup' | 'cached'; lookupId?: number; mealNote?: string } | null>(null)
  const [meal, setMeal] = useState<{ slot: Slot; foods: any[] } | null>(null)
  const [lookingUp, setLookingUp] = useState(false)
  const [lookupMsg, setLookupMsg] = useState('')
  const [err, setErr] = useState('')
  const dateRef = useRef<HTMLInputElement>(null)

  const load = useCallback(
    () => api(`/day/${day}`).then((d) => { setData(d); setDone(!!d.complete); setErr('') }).catch((e) => setErr(e.message)),
    [day],
  )
  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (q.trim().length < 2) { setResults([]); return }
    const t = setTimeout(() => api(`/foods/search?q=${encodeURIComponent(q)}`).then(setResults).catch(() => {}), 250)
    return () => clearTimeout(t)
  }, [q])

  const toggle = (key: string) => {
    setOpen(open === key ? null : key)
    setQ(''); setResults([]); setManual(false)
  }

  async function logFood(slot: Slot, food: any) {
    if (food.source_type === 'recipe' && !food.verified) { setVerify({ slot, food }); return }
    if (food.source_type === 'restaurant' && !food.verified) { setRcheck({ slot, items: [food], mode: 'cached' }); return }
    setPick({ slot, food })
  }

  async function confirmPick(amount: number, split: number | null, remember: boolean) {
    if (!pick) return
    const { slot, food } = pick
    if (remember && split) {
      await api(`/foods/${food.id}/servings`, { method: 'PUT', body: JSON.stringify({ servings: split }) })
    }
    await api('/logs', {
      method: 'POST',
      body: JSON.stringify({ date: day, meal_slot: slot, food_id: food.id, servings: amount, split: split ?? undefined }),
    })
    setPick(null); setQ(''); setResults([]); load()
  }

  async function addManual(slot: Slot, e: React.FormEvent) {
    e.preventDefault()
    const num = (s: string) => Number(s) || 0
    const base = { name: m.name, calories: num(m.calories), protein_g: num(m.protein_g), carbs_g: num(m.carbs_g), fat_g: num(m.fat_g) }
    if (m.save) {
      const { id } = await api('/foods', { method: 'POST', body: JSON.stringify(base) })
      await api('/logs', { method: 'POST', body: JSON.stringify({ date: day, meal_slot: slot, food_id: id }) })
    } else {
      await api('/logs', { method: 'POST', body: JSON.stringify({ date: day, meal_slot: slot, ...base }) })
    }
    setM({ name: '', calories: '', protein_g: '', carbs_g: '', fat_g: '', save: true })
    setManual(false); load()
  }

  async function addExercise(e: React.FormEvent) {
    e.preventDefault()
    const dist = Number(ex.distance) || undefined
    try {
      await api('/exercise', {
        method: 'POST',
        body: JSON.stringify({
          date: day, type: ex.type,
          distance_km: dist && (imp ? dist * 1.60934 : dist),
          duration_min: Number(ex.minutes) || undefined,
          kcal_burned: Number(ex.kcal) || undefined,
        }),
      })
      setEx({ ...ex, distance: '', minutes: '', kcal: '' })
      load()
    } catch (e: any) {
      setErr(e.message)
    }
  }

  async function lookUp(slot: Slot) {
    setLookingUp(true); setLookupMsg('')
    try {
      const r = await api('/restaurant/lookup', { method: 'POST', body: JSON.stringify({ query: q.trim() }) })
      if (!r.found) setLookupMsg('Couldn’t find reliable numbers for that. Try the exact menu name, or add it manually.')
      else setRcheck({ slot, items: r.items, mode: 'lookup', lookupId: r.lookup_id, mealNote: r.meal_note })
    } catch (e: any) {
      setLookupMsg(e.message)
    } finally {
      setLookingUp(false)
    }
  }

  async function confirmMeal(amounts: number[]) {
    if (!meal) return
    for (let i = 0; i < meal.foods.length; i++) {
      if (amounts[i] <= 0) continue
      await api('/logs', {
        method: 'POST',
        body: JSON.stringify({ date: day, meal_slot: meal.slot, food_id: meal.foods[i].id, servings: amounts[i] }),
      })
    }
    setMeal(null); setQ(''); setResults([]); load()
  }

  function afterRestaurant(foods: any[]) {
    if (!rcheck) return
    if (foods.length === 1) setPick({ slot: rcheck.slot, food: foods[0] })
    else setMeal({ slot: rcheck.slot, foods })
    setRcheck(null)
  }

  function afterVerify(food: any) {
    if (!verify) return
    setPick({ slot: verify.slot, food })
    setVerify(null)
  }

  const t = data?.totals
  const tg = data?.target
  const logs: any[] = data?.logs ?? []
  const burned: number = data?.exercise_burned ?? 0
  const hasAny = logs.length > 0

  return (
    <div>
      <header className="top">
        <div>
          <h1>{day === today() ? 'Today' : 'Diary'}</h1>
          <p className="note">{longDate(day)}</p>
        </div>
        <div className="actions">
          <button
            className={done ? 'markbtn done' : 'markbtn'}
            title={done ? 'This day is marked as fully logged. Tap to undo.' : 'Mark this day as fully logged so adaptive goals can use it'}
            onClick={() => api(`/day/${day}/complete`, { method: done ? 'DELETE' : 'PUT' }).then(() => setDone(!done)).catch((e) => setErr(e.message))}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6L9 17l-5-5" />
            </svg>
            <span className="lbl">{done ? 'Logged' : 'Mark logged'}</span>
          </button>
          <button className="iconbtn" aria-label="Pick a date" onClick={() => dateRef.current?.showPicker?.()}>
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="3" /><path d="M16 2v4M8 2v4M3 10h18" />
            </svg>
          </button>
        </div>
        <input ref={dateRef} className="hidden-date" type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} />
      </header>
      {err && <p className="error">{err}</p>}
      <InstallHelp banner />

      <div className="dash">
      <div className="side">
      {t && (
        <section className="card">
          <div className="hero">
            <Ring value={t.calories} target={tg?.calories} />
            <div className="macros">
              <MacroBar label="Protein" value={t.protein_g} target={tg?.protein_g} color="var(--protein)" />
              <MacroBar label="Carbs" value={t.carbs_g} target={tg?.carbs_g} color="var(--carbs)" />
              <MacroBar label="Fat" value={t.fat_g} target={tg?.fat_g} color="var(--fat)" />
            </div>
          </div>
          <div className="trio">
            <div><span>Eaten</span><b>{Math.round(t.calories)}</b></div>
            <div><span>Burned</span><b>{burned}</b></div>
            <div><span>Goal</span><b>{tg ? Math.round(tg.calories) : '—'}</b></div>
          </div>
          {!tg && <p className="note">Log a weight to see your targets.</p>}
          {tg?.method === 'adaptive' && <p className="note">Goal uses your measured maintenance (adaptive), which already reflects your exercise.</p>}
          {tg?.exercise_bonus > 0 && <p className="note">Includes +{tg.exercise_bonus} kcal from exercise.</p>}
          {tg?.adaptive_withdrawn && <p className="warn">Adaptive goals are paused because recent logging no longer qualifies. Using the formula.</p>}
          {tg?.floor_applied && <p className="warn">Your goal rate would go below the safe minimum, so the minimum was used.</p>}
          {data.has_estimates && <p className="warn">⚠ Includes estimated items, so totals aren’t exact.</p>}
        </section>
      )}

      </div>
      <div className="main">
      <div className="sectionhead">
        <h2>Food diary</h2>
      </div>

      <section className="card list">
        {SLOTS.map((s) => {
          const items = logs.filter((l) => l.meal_slot === s)
          const kcal = items.reduce((a, l) => a + Number(l.calories), 0)
          const prot = items.reduce((a, l) => a + Number(l.protein_g), 0)
          const isOpen = open === s
          return (
            <div key={s} className="meal">
              <button className="mealhead" onClick={() => toggle(s)} aria-expanded={isOpen}>
                <span className="tile">{EMOJI[s]}</span>
                <span className="mealtext">
                  <b>{s[0].toUpperCase() + s.slice(1)}</b>
                  <small>{items.length ? `${items.map((i) => i.name).join(', ')} · ${Math.round(prot)}g protein` : EMPTY_HINT[s]}</small>
                </span>
                <span className="kcal">{Math.round(kcal)} kcal</span>
                <span className={isOpen ? 'chev open' : 'chev'}>›</span>
              </button>
              {isOpen && (
                <div className="mealbody">
                  {items.map((l) => (
                    <div key={l.id} className="logrow">
                      <span>{l.name}{l.is_estimate ? ' ⚠' : ''}</span>
                      <span className="kcal">{Math.round(l.calories)} kcal</span>
                      <button className="link" aria-label="Remove" onClick={() => api(`/logs/${l.id}`, { method: 'DELETE' }).then(load)}>✕</button>
                    </div>
                  ))}
                  <input placeholder="Search meals, recipes, restaurants…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
                  {results.map((r) => (
                    <button key={r.id} className="result" onClick={() => logFood(s, r)}>
                      <span>{r.name}</span>
                      <small>
                        {r.source_type === 'recipe' ? r.book_title : r.source_type === 'restaurant' ? r.restaurant : 'My food'}
                        {' · '}{Math.round(r.calories)} kcal{r.is_estimate ? ' · estimate' : ''}{r.verified ? ' · ✓' : ''}
                      </small>
                    </button>
                  ))}
                  {q.trim().length >= 3 && (
                    <button className="link" disabled={lookingUp} onClick={() => lookUp(s)}>
                      {lookingUp ? 'Looking it up…' : `🔎 Look up “${q.trim()}” online`}
                    </button>
                  )}
                  {q.trim().length >= 3 && !lookingUp && !lookupMsg && (
                    <p className="note">Tip: you can describe a whole order, like “Panda Express plate with teriyaki chicken and chow mein”, or a variant like “Domino’s large pepperoni, 2 slices”.</p>
                  )}
                  {lookupMsg && <p className="note">{lookupMsg}</p>}
                  <button className="link" onClick={() => setManual(!manual)}>{manual ? 'Cancel' : '+ Add manually'}</button>
                  {manual && (
                    <form onSubmit={(e) => addManual(s, e)}>
                      <input placeholder="Name" value={m.name} onChange={(e) => setM({ ...m, name: e.target.value })} required />
                      <input type="number" placeholder="Calories" value={m.calories} onChange={(e) => setM({ ...m, calories: e.target.value })} required />
                      <div className="row">
                        <input type="number" placeholder="Protein g" value={m.protein_g} onChange={(e) => setM({ ...m, protein_g: e.target.value })} />
                        <input type="number" placeholder="Carbs g" value={m.carbs_g} onChange={(e) => setM({ ...m, carbs_g: e.target.value })} />
                        <input type="number" placeholder="Fat g" value={m.fat_g} onChange={(e) => setM({ ...m, fat_g: e.target.value })} />
                      </div>
                      <label className="row"><input type="checkbox" checked={m.save} onChange={(e) => setM({ ...m, save: e.target.checked })} />Save for reuse</label>
                      <button type="submit">Add</button>
                    </form>
                  )}
                </div>
              )}
            </div>
          )
        })}

        <div className="meal">
          <button className="mealhead" onClick={() => toggle('exercise')} aria-expanded={open === 'exercise'}>
            <span className="tile">{EMOJI.exercise}</span>
            <span className="mealtext">
              <b>Exercise</b>
              <small>{data?.exercise?.length ? data.exercise.map((x: any) => x.type).join(', ') : 'Log a workout'}</small>
            </span>
            <span className="kcal">{burned} kcal</span>
            <span className={open === 'exercise' ? 'chev open' : 'chev'}>›</span>
          </button>
          {open === 'exercise' && (
            <div className="mealbody">
              {(data?.exercise ?? []).map((x: any) => (
                <div key={x.id} className="logrow">
                  <span>{x.type}{x.distance_km ? ` ${(imp ? x.distance_km / 1.60934 : x.distance_km).toFixed(1)} ${imp ? 'mi' : 'km'}` : ''}</span>
                  <span className="kcal">{Math.round(x.kcal_burned)} kcal</span>
                  <button className="link" aria-label="Remove" onClick={() => api(`/exercise/${x.id}`, { method: 'DELETE' }).then(load)}>✕</button>
                </div>
              ))}
              <details className="how">
                <summary>How are these calories estimated?</summary>
                <p className="note">
                  We estimate the calories burned <b>above what you’d burn at rest</b>, using your most recent logged weight.
                </p>
                <ul className="note">
                  <li><b>Running</b> with a distance: about 1 kcal per kg per km (roughly 0.63 per lb per mile). A 3-mile run at 147 lb is about 320 kcal.</li>
                  <li><b>Walking</b> with a distance: about half that.</li>
                  <li><b>With only a time:</b> typical effort levels are used (running about 8 METs, walking 2.5, cycling and swimming 5, HIIT 7, strength training 3).</li>
                </ul>
                <p className="note">
                  Real burn changes with pace, hills, and fitness, so treat it as roughly ±20–30%. If your watch or machine
                  gives a number, type it into “Calories burned” to override the estimate. Whether any of it raises your daily
                  goal is controlled by “Eat back exercise calories” in Profile (none, half, or all), and adaptive goals already
                  account for your usual exercise.
                </p>
              </details>
              <form onSubmit={addExercise}>
                <select value={ex.type} onChange={(e) => setEx({ ...ex, type: e.target.value })}>
                  {KINDS.map((k) => <option key={k}>{k}</option>)}
                </select>
                {DISTANCE_KINDS.includes(ex.type) && (
                  <input type="number" step="0.1" placeholder={`Distance (${imp ? 'mi' : 'km'})`} value={ex.distance}
                    onChange={(e) => setEx({ ...ex, distance: e.target.value })} />
                )}
                <input type="number" placeholder="Minutes" value={ex.minutes} onChange={(e) => setEx({ ...ex, minutes: e.target.value })} />
                <input type="number" placeholder="Calories burned (optional override)" value={ex.kcal} onChange={(e) => setEx({ ...ex, kcal: e.target.value })} />
                <button type="submit">Add exercise</button>
              </form>
            </div>
          )}
        </div>
      </section>

      {!hasAny && open === null && (
        <button className="cta" onClick={() => toggle(defaultSlot())}>＋ Log your first meal</button>
      )}

      </div>
      </div>
      {verify && <VerifyModal food={verify.food} onDone={afterVerify} onCancel={() => setVerify(null)} />}
      {rcheck && <RestaurantModal items={rcheck.items} mode={rcheck.mode} lookupId={rcheck.lookupId} mealNote={rcheck.mealNote} onDone={afterRestaurant} onCancel={() => setRcheck(null)} />}
      {meal && <MealSheet foods={meal.foods} slot={meal.slot} onConfirm={confirmMeal} onCancel={() => setMeal(null)} />}
      {pick && <ServingSheet food={pick.food} slot={pick.slot} onConfirm={confirmPick} onCancel={() => setPick(null)} />}
    </div>
  )
}
