import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
)

const API = import.meta.env.VITE_API_URL as string

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  const res = await fetch(`${API}/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ? JSON.stringify(body.detail) : `Request failed (${res.status})`)
  }
  return res.json()
}

// Unit helpers (data is stored metric).
export const kgToLb = (kg: number) => kg * 2.20462
export const lbToKg = (lb: number) => lb / 2.20462
export const cmToIn = (cm: number) => cm / 2.54
export const inToCm = (i: number) => i * 2.54
export const today = () => new Date().toISOString().slice(0, 10)
