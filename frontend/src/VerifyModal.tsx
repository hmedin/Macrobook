import { useEffect, useState } from 'react'
import { api } from './lib'
import { cachePages, getPageImage, getPdf, sha256 } from './localpdf'
import PdfPage from './PdfPage'

// First-use check for a parsed recipe: original page beside what we read.
// Hands back the food to log (the original, or an edited personal copy).
export default function VerifyModal({ food, onDone, onCancel }: {
  food: any
  onDone: (food: any) => void
  onCancel: () => void
}) {
  // Small page image (preferred) or a legacy whole-PDF copy; null = not on this device.
  const [img, setImg] = useState<string | null | undefined>(undefined)
  const [legacy, setLegacy] = useState<Blob | null>(null)
  const [progress, setProgress] = useState('')
  const [v, setV] = useState({
    calories: String(Math.round(food.calories)), protein_g: String(Math.round(food.protein_g)),
    carbs_g: String(Math.round(food.carbs_g)), fat_g: String(Math.round(food.fat_g)),
  })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function loadOrigin() {
    const page = await getPageImage(food.file_hash, food.source_page).catch(() => undefined)
    if (page) { setImg(URL.createObjectURL(page)); return }
    const pdf = await getPdf(food.file_hash).catch(() => undefined)
    if (pdf) { setLegacy(pdf); setImg(null); return }
    setImg(null)
  }
  useEffect(() => {
    loadOrigin()
    return () => { setImg((u) => { if (u) URL.revokeObjectURL(u); return u }) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [food.file_hash, food.source_page])

  const changed =
    Number(v.calories) !== Math.round(food.calories) || Number(v.protein_g) !== Math.round(food.protein_g) ||
    Number(v.carbs_g) !== Math.round(food.carbs_g) || Number(v.fat_g) !== Math.round(food.fat_g)

  async function attach(file: File) {
    if ((await sha256(file)) !== food.file_hash) { setErr('That file doesn’t match this cookbook.'); return }
    setErr('')
    try {
      const { pages } = await api(`/books/${food.book_id}/pages`)
      await cachePages(file, food.file_hash, pages, (d, t) => setProgress(`Saving small page images… ${d}/${t}`))
      setProgress('')
      await loadOrigin()
    } catch (e: any) {
      setProgress(''); setErr(e.message || 'Could not read that file')
    }
  }

  async function confirm() {
    setBusy(true); setErr('')
    try {
      if (changed) {
        // Don't alter the shared recipe; save the corrected numbers as the user's own food.
        const { id } = await api('/foods', {
          method: 'POST',
          body: JSON.stringify({
            name: `${food.name} (edited)`, serving_desc: food.serving_desc,
            calories: Number(v.calories) || 0, protein_g: Number(v.protein_g) || 0,
            carbs_g: Number(v.carbs_g) || 0, fat_g: Number(v.fat_g) || 0,
            is_batch: !!food.is_batch, book_servings: food.book_servings ?? undefined,
          }),
        })
        onDone({
          ...food, id, name: `${food.name} (edited)`, source_type: 'custom', verified: true, user_servings: null,
          calories: Number(v.calories) || 0, protein_g: Number(v.protein_g) || 0,
          carbs_g: Number(v.carbs_g) || 0, fat_g: Number(v.fat_g) || 0,
        })
      } else {
        await api(`/foods/${food.id}/verify`, { method: 'POST' })
        onDone({ ...food, verified: true })
      }
    } catch (e: any) {
      setErr(e.message); setBusy(false)
    }
  }

  const field = (k: keyof typeof v, label: string) => (
    <label>{label}<input type="number" value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} /></label>
  )

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Check this recipe">
      <div className="modal">
        <div className="modalhead">
          <div>
            <h2>Check this recipe</h2>
            <p className="note">First time logging it. Compare what we read with the book.</p>
          </div>
          <button className="link" onClick={onCancel} aria-label="Close">✕</button>
        </div>
        <div className="compare">
          <div className="origin">
            {img === undefined && <p className="note">Loading…</p>}
            {img && <img className="pdfpage" src={img} alt={`Page ${food.source_page + 1} of ${food.book_title ?? 'the cookbook'}`} />}
            {img === null && legacy && <PdfPage blob={legacy} page={food.source_page} />}
            {img === null && !legacy && (
              <div className="note">
                {progress ? <p>{progress}</p> : (
                  <>
                    <p>The original page isn’t saved on this device. Choose the cookbook PDF again to see it side by side. The app only keeps small images of the recipe pages, not the whole PDF.</p>
                    <label className="filebtn">Choose PDF
                      <input type="file" accept="application/pdf" hidden onChange={(e) => e.target.files?.[0] && attach(e.target.files[0])} />
                    </label>
                  </>
                )}
              </div>
            )}
          </div>
          <div className="parsed">
            <h3>What we read</h3>
            <p><b>{food.name}</b></p>
            <p className="note">{food.serving_desc} · {food.book_title}{food.source_page != null ? ` · page ${food.source_page + 1}` : ''}</p>
            <div className="fields">
              {field('calories', 'Calories')}
              {field('protein_g', 'Protein g')}
              {field('carbs_g', 'Carbs g')}
              {field('fat_g', 'Fat g')}
            </div>
            {changed && <p className="warn">You changed the numbers. They’ll be saved as your own copy, and the original stays untouched.</p>}
            {err && <p className="error">{err}</p>}
            <button disabled={busy} onClick={confirm}>{changed ? 'Save my version & log it' : 'Looks right, log it'}</button>
            <button className="link" onClick={onCancel}>Cancel</button>
          </div>
        </div>
      </div>
    </div>
  )
}
