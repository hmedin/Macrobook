import { useEffect, useState } from 'react'

type Platform = 'ios' | 'android' | 'desktop'

function detectPlatform(): Platform {
  const ua = navigator.userAgent
  if (/iphone|ipad|ipod/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) return 'ios'
  if (/android/i.test(ua)) return 'android'
  return 'desktop'
}

const isInstalled = () =>
  window.matchMedia('(display-mode: standalone)').matches || (navigator as any).standalone === true

const DISMISS_KEY = 'installTipDismissed'

// Install-as-an-app instructions. `banner` is the small dismissible tip on Today (phones only).
export default function InstallHelp({ banner = false }: { banner?: boolean }) {
  const platform = detectPlatform()
  const installed = isInstalled()
  const [deferred, setDeferred] = useState<any>(null)
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem(DISMISS_KEY) === '1' } catch { return false }
  })

  useEffect(() => {
    const onPrompt = (e: Event) => { e.preventDefault(); setDeferred(e) }
    window.addEventListener('beforeinstallprompt', onPrompt)
    return () => window.removeEventListener('beforeinstallprompt', onPrompt)
  }, [])

  if (banner && (installed || dismissed || platform === 'desktop')) return null

  const dismiss = () => {
    setDismissed(true)
    try { localStorage.setItem(DISMISS_KEY, '1') } catch { /* private mode */ }
  }

  async function install() {
    if (!deferred) return
    deferred.prompt()
    await deferred.userChoice.catch(() => {})
    setDeferred(null)
  }

  const steps =
    platform === 'ios' ? (
      <ol>
        <li>Open this page in <b>Safari</b>.</li>
        <li>Tap the <b>Share</b> button (the square with an arrow, at the bottom or top).</li>
        <li>Scroll and tap <b>Add to Home Screen</b>, then <b>Add</b>.</li>
      </ol>
    ) : platform === 'android' ? (
      <ol>
        <li>Open this page in <b>Chrome</b>.</li>
        <li>Tap the <b>⋮</b> menu in the top right.</li>
        <li>Tap <b>Install app</b> (or <b>Add to Home screen</b>), then <b>Install</b>.</li>
      </ol>
    ) : (
      <ol>
        <li>In Chrome or Edge, look for the <b>install icon</b> at the right end of the address bar.</li>
        <li>Or open the browser menu and choose <b>Install Macrobook</b>.</li>
      </ol>
    )

  const body = (
    <>
      {installed ? (
        <p className="note">✓ You’re using the installed app.</p>
      ) : (
        <>
          {deferred && <button onClick={install}>Install Macrobook</button>}
          {steps}
        </>
      )}
      <p className="note">
        Installed, Macrobook opens full screen from your home screen like any other app. On iPhone the installed app keeps its
        own sign-in, so sign in again once inside it. If Google or Discord sign-in doesn’t work in the installed app, use email and password.
      </p>
    </>
  )

  if (banner) {
    return (
      <section className="card tip">
        <div className="tiphead">
          <b>📲 Add Macrobook to your home screen</b>
          <button className="link" onClick={dismiss} aria-label="Dismiss">✕</button>
        </div>
        <details>
          <summary>Show me how</summary>
          {body}
        </details>
      </section>
    )
  }

  return (
    <section className="card narrow goalcard">
      <h2>Install on your phone</h2>
      {body}
    </section>
  )
}
