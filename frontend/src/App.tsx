import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase, api } from './lib'
import Login from './screens/Login'
import Setup from './screens/Setup'
import Today from './screens/Today'
import Weight from './screens/Weight'
import Books from './screens/Books'
import Goals from './screens/Goals'
import InstallHelp from './InstallHelp'
import DangerZone, { LegalLinks } from './DangerZone'
import { ICONS } from './components'
import './App.css'

type Tab = 'today' | 'books' | 'weight' | 'profile'

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)
  const [profile, setProfile] = useState<any>(undefined)
  const [tab, setTab] = useState<Tab>('today')

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setReady(true)
    })
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (session) api('/profile').then(setProfile).catch(() => setProfile(null))
  }, [session])

  if (!ready) return null
  if (!session) return <Login />
  if (profile === undefined) return <p className="center">Loading…</p>
  if (!profile) return <Setup onDone={() => api('/profile').then(setProfile)} />

  return (
    <div className="app">
      <main>
        {tab === 'today' && <Today profile={profile} />}
        {tab === 'books' && <Books />}
        {tab === 'weight' && <Weight profile={profile} />}
        {tab === 'profile' && (
          <>
            <InstallHelp />
            <Goals profile={profile} />
            <Setup existing={profile} onDone={() => api('/profile').then(setProfile)}>
              <button className="link" onClick={() => supabase.auth.signOut()}>Sign out</button>
            </Setup>
            <DangerZone />
            <LegalLinks />
          </>
        )}
      </main>
      <nav>
        <div className="tabs">
          {(['today', 'books', 'weight', 'profile'] as Tab[]).map((t) => (
            <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
              {ICONS[t]}
              {t[0].toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </nav>
    </div>
  )
}
