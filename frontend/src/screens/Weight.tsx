import { useEffect, useState } from 'react'
import { api, kgToLb, lbToKg, today } from '../lib'

const fmtDate = (iso: string) =>
  new Date(iso + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

export default function Weight({ profile }: { profile: any }) {
  const imp = profile.unit_pref === 'imperial'
  const unit = imp ? 'lb' : 'kg'
  const conv = (kg: number) => (imp ? kgToLb(kg) : kg)
  const [rows, setRows] = useState<any[]>([])
  const [val, setVal] = useState('')
  const [date, setDate] = useState(today())
  const [err, setErr] = useState('')
  const load = () => api('/weights').then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])

  async function add(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    try {
      await api('/weights', {
        method: 'PUT',
        body: JSON.stringify({ date, weight_kg: imp ? lbToKg(Number(val)) : Number(val) }),
      })
      setVal(''); load()
    } catch (e: any) {
      setErr(e.message)
    }
  }

  const trend = rows.map((r) => conv(r.trend_kg))
  const raw = rows.map((r) => conv(r.weight_kg))
  const last = rows[rows.length - 1]
  const first = rows[0]

  // Weekly rate from the smoothed trend over roughly the last 14 days.
  let weekly: number | null = null
  if (rows.length >= 2) {
    const endT = new Date(last.date).getTime()
    const base = rows.find((r) => endT - new Date(r.date).getTime() <= 14 * 864e5) ?? first
    const days = (endT - new Date(base.date).getTime()) / 864e5
    if (days >= 4) weekly = ((conv(last.trend_kg) - conv(base.trend_kg)) / days) * 7
  }
  const signed = (n: number) => `${n > 0 ? '+' : ''}${n.toFixed(1)}`

  const all = [...trend, ...raw]
  const pad = all.length ? Math.max((Math.max(...all) - Math.min(...all)) * 0.15, 0.5) : 0
  const lo = all.length ? Math.min(...all) - pad : 0
  const hi = all.length ? Math.max(...all) + pad : 1
  const x = (i: number) => (rows.length < 2 ? 50 : (i / (rows.length - 1)) * 100)
  const y = (v: number) => 100 - ((v - lo) / (hi - lo || 1)) * 100
  const line = trend.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join(' ')
  const dots = raw.map((v, i) => `M${x(i)},${y(v)}h0`).join(' ')

  return (
    <div>
      <header className="top">
        <div>
          <h1>Weight</h1>
          <p className="note">The smoothed trend, not daily swings, drives your goals.</p>
        </div>
      </header>
      {err && <p className="error">{err}</p>}

      {last && (
        <section className="card">
          <div className="trio plain">
            <div><span>Trend</span><b>{conv(last.trend_kg).toFixed(1)} {unit}</b></div>
            <div><span>Since start</span><b>{signed(conv(last.trend_kg) - conv(first.trend_kg))} {unit}</b></div>
            <div><span>Per week</span><b>{weekly === null ? '—' : `${signed(weekly)} ${unit}`}</b></div>
          </div>
        </section>
      )}

      <form className="card weightform" onSubmit={add}>
        <input type="date" value={date} max={today()} onChange={(e) => e.target.value && setDate(e.target.value)} />
        <input type="number" step="0.1" placeholder={`Weight (${unit})`} value={val} onChange={(e) => setVal(e.target.value)} required />
        <button type="submit">Log weight</button>
      </form>

      {rows.length > 0 && (
        <section className="card">
          <div className="chartwrap">
            <span className="ylab hi">{hi.toFixed(0)}</span>
            <span className="ylab lo">{lo.toFixed(0)}</span>
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="wchart" role="img" aria-label="Weight trend chart">
              <path d={dots} fill="none" stroke="#94a3a0" strokeWidth="6" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
              <path d={line} fill="none" stroke="var(--green)" strokeWidth="2.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            </svg>
          </div>
          <div className="xlabs"><span>{fmtDate(first.date)}</span><span>{fmtDate(last.date)}</span></div>
          <p className="note">Dots are daily weigh-ins; the green line is the trend.</p>
        </section>
      )}

      {rows.length > 0 && (
        <section className="card list">
          <h3 style={{ padding: '10px 10px 0' }}>Recent</h3>
          {[...rows].reverse().slice(0, 10).map((r) => (
            <div key={r.date} className="logrow plainrow">
              <span>{fmtDate(r.date)}</span>
              <span className="kcal">{conv(r.weight_kg).toFixed(1)} {unit}</span>
              <span className="kcal">trend {conv(r.trend_kg).toFixed(1)}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
