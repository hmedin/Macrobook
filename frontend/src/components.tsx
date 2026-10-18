export function Ring({ value, target }: { value: number; target?: number }) {
  const r = 62, c = 2 * Math.PI * r
  const pct = target ? Math.min(1, value / target) : 0
  const over = target ? value > target : false
  const left = target ? Math.round(target - value) : null
  return (
    <div className="ring">
      <svg width="150" height="150" viewBox="0 0 150 150" role="img" aria-label="Calories progress">
        <circle cx="75" cy="75" r={r} fill="none" stroke="var(--track)" strokeWidth="12" />
        <circle cx="75" cy="75" r={r} fill="none" stroke={over ? '#dc2626' : 'var(--green)'} strokeWidth="12"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - pct)}
          style={{ transition: 'stroke-dashoffset .5s ease' }} />
      </svg>
      <div className="mid">
        <span className="big">{left === null ? Math.round(value) : Math.abs(left)}</span>
        <span className="sub">{left === null ? 'kcal eaten' : left >= 0 ? 'kcal left' : 'kcal over'}</span>
      </div>
    </div>
  )
}

export function MacroBar({ label, value, target, color }: { label: string; value: number; target?: number; color: string }) {
  const pct = target ? Math.min(100, (value / target) * 100) : 0
  return (
    <div className="bar">
      <div className="barhead">
        <span>{label}</span>
        <span><b>{Math.round(value)}</b>{target ? ` / ${Math.round(target)}g` : 'g'}</span>
      </div>
      <div className="track">
        <div className={target && value > target ? 'fill over' : 'fill'} style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}

const icon = (d: string) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
)
export const ICONS = {
  today: icon('M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10'),
  books: icon('M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14zM20 17v4H6.5A2.5 2.5 0 0 1 4 19.5'),
  weight: icon('M3 17l6-6 4 4 8-8M15 7h6v6'),
  profile: icon('M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z'),
}
