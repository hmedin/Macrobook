import { useState } from 'react'
import { supabase } from '../lib'

const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
    <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z"/>
    <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z"/>
    <path fill="#FBBC05" d="M10.5 28.7a14.5 14.5 0 0 1 0-9.4l-7.9-6.1a24 24 0 0 0 0 21.6l7.9-6.1z"/>
    <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.9 2.3-8.4 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z"/>
  </svg>
)
const DiscordIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="#5865F2" aria-hidden="true">
    <path d="M20.3 4.4A19.8 19.8 0 0 0 15.4 3l-.2.5a18 18 0 0 0-6.4 0L8.6 3a19.8 19.8 0 0 0-4.9 1.4C.6 9 0 13.5.3 18a20 20 0 0 0 6 3l1.3-2.1a13 13 0 0 1-2-.9l.5-.4a14 14 0 0 0 11.8 0l.5.4c-.6.4-1.3.7-2 .9L17.7 21a20 20 0 0 0 6-3c.4-5.200-.6-9.700-3.400-13.600zM8.500 15.300c-1.100 0-2-1-2-2.200s.9-2.200 2-2.200 2 1 2 2.200-.9 2.200-2 2.200zm7 0c-1.100 0-2-1-2-2.200s.9-2.200 2-2.200 2 1 2 2.200-.9 2.200-2 2.200z"/>
  </svg>
)

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [msg, setMsg] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setMsg('')
    const { error } =
      mode === 'in'
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password })
    if (error) setMsg(error.message)
    else if (mode === 'up') setMsg('Check your email to confirm, then sign in.')
  }

  async function oauth(provider: 'google' | 'discord') {
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: window.location.origin },
    })
    if (error) setMsg(error.message)
  }

  return (
    <div className="login">
      <form className="card" onSubmit={submit}>
        <img className="logo" src="/icon.svg" alt="" />
        <h1>Calorie Tracker</h1>
        <p className="tag">Eat what you love. Hit your goals.</p>
        <button type="button" className="social" onClick={() => oauth('google')}><GoogleIcon /> Continue with Google</button>
        <button type="button" className="social" onClick={() => oauth('discord')}><DiscordIcon /> Continue with Discord</button>
        <div className="divider">or</div>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="password" placeholder="Password (8+ chars)" value={password} minLength={8}
          onChange={(e) => setPassword(e.target.value)} required />
        <button type="submit">{mode === 'in' ? 'Sign in' : 'Create account'}</button>
        <button type="button" className="link" onClick={() => setMode(mode === 'in' ? 'up' : 'in')}>
          {mode === 'in' ? 'Need an account? Sign up' : 'Have an account? Sign in'}
        </button>
        {msg && <p className="note">{msg}</p>}
      </form>
    </div>
  )
}
