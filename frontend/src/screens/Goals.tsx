import { useCallback, useEffect, useState } from 'react'
import { api, kgToLb } from '../lib'

function Meter({ label, value, needed }: { label: string; value: number; needed: number }) {
  const pct = Math.min(100, (value / needed) * 100)
  return (
    <div className="bar">
      <div className="barhead">
        <span>{label}</span>
        <span><b>{Math.min(value, needed)}</b> / {needed}</span>
      </div>
      <div className="track"><div className="fill" style={{ width: `${pct}%`, background: 'var(--green)' }} /></div>
    </div>
  )
}

export default function Goals({ profile }: { profile: any }) {
  const imp = profile.unit_pref === 'imperial'
  const [goal, setGoal] = useState<any>(null)
  const [ad, setAd] = useState<any>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [g, a] = await Promise.all([api('/goal'), api('/goal/adaptive')])
      setGoal(g); setAd(a); setErr('')
    } catch (e: any) {
      setErr(e.message)
    }
  }, [])
  useEffect(() => { load() }, [load])

  async function setMode(body: { mode?: 'tdee' | 'adaptive'; opt_out?: boolean }) {
    setBusy(true); setErr('')
    try {
      await api('/goal/mode', { method: 'PUT', body: JSON.stringify(body) })
      await load()
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (err && !goal) return <section className="card narrow goalcard"><p className="note">Log a weight to see your numbers.</p></section>
  if (!goal || !ad) return null

  const weight = imp ? kgToLb(goal.trend_weight_kg) : goal.trend_weight_kg
  const diff = ad.measured_maintenance ? ad.measured_maintenance - goal.formula_maintenance : null
  const usingAdaptive = goal.method === 'adaptive'

  return (
    <>
      <section className="card narrow goalcard">
        <h2>Your numbers</h2>
        <div className="trio plain">
          <div><span>Daily goal</span><b>{goal.calories}</b></div>
          <div><span>Maintenance</span><b>{goal.maintenance}</b></div>
          <div><span>Trend weight</span><b>{weight.toFixed(1)} {imp ? 'lb' : 'kg'}</b></div>
        </div>
        <p className="note">
          Based on {usingAdaptive ? 'your measured maintenance (adaptive).' : 'the standard formula (Mifflin-St Jeor) and your activity level.'}
        </p>
        {goal.floor_applied && <p className="warn">Your goal rate would go below the safe minimum, so the minimum is used.</p>}
        {goal.adaptive_withdrawn && (
          <p className="warn">Adaptive goals were switched off for now because your recent logging no longer qualifies. You’re back on the formula.</p>
        )}
      </section>

      <section className="card narrow goalcard">
        <h2>Adaptive goals</h2>
        <p className="note">
          After a few weeks, the app can work out your real maintenance from what you ate and how your weight trend moved,
          instead of relying on a formula’s estimate.
        </p>

        {ad.opt_out ? (
          <>
            <p>You’ve chosen to stay on the formula.</p>
            <button className="ghost" disabled={busy} onClick={() => setMode({ opt_out: false })}>Allow adaptive goals again</button>
          </>
        ) : !ad.eligible ? (
          <>
            <p className="note">Not available yet. It needs enough data to be trustworthy:</p>
            <Meter label="Days of tracking" value={ad.progress.span_days} needed={ad.progress.span_needed} />
            <Meter label="Fully logged days" value={ad.progress.complete_days} needed={ad.progress.complete_needed} />
            <Meter label="Weigh-ins" value={ad.progress.weighins} needed={ad.progress.weighins_needed} />
            <p className="note">Tap “Mark logged” on Today at the end of each day you logged everything.</p>
            <button className="link" disabled={busy} onClick={() => setMode({ opt_out: true })}>Don’t offer adaptive goals</button>
          </>
        ) : (
          <>
            <div className="compare2">
              <div><span>Formula says</span><b>{goal.formula_maintenance}</b></div>
              <div><span>Your data says</span><b>{ad.measured_maintenance}</b></div>
              {diff !== null && <div><span>Difference</span><b>{diff > 0 ? '+' : ''}{diff}</b></div>}
            </div>
            <p className="warn">⚠ {ad.warning}</p>
            {usingAdaptive ? (
              <>
                <p className="pill">Using your measured number</p>
                <button className="ghost" disabled={busy} onClick={() => setMode({ mode: 'tdee' })}>Switch back to the formula</button>
              </>
            ) : (
              <button disabled={busy} onClick={() => setMode({ mode: 'adaptive' })}>Use my measured number</button>
            )}
            <button className="link" disabled={busy} onClick={() => setMode({ mode: 'tdee', opt_out: true })}>
              Always stay on the formula
            </button>
          </>
        )}
        {err && <p className="error">{err}</p>}
      </section>
    </>
  )
}
