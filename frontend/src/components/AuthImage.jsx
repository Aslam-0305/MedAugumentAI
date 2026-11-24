import { useEffect, useState } from 'react'
import { http } from '../api/client.js'

/** Fetches an image through axios (so the API key header is sent) and shows it in a light-box frame. */
export function previewRequest(id, params) {
  return () => http.get(`/images/${id}/preview`, { params, responseType: 'blob' }).then((r) => r.data)
}
export function augmentedPreviewRequest(body) {
  return () => http.post('/augmentation/preview', body, { responseType: 'blob' }).then((r) => r.data)
}

export default function AuthImage({ request, cacheKey, alt, className = '' }) {
  const [url, setUrl] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let revoked = false
    let objectUrl = null
    setUrl(null)
    setFailed(false)
    request()
      .then((blob) => {
        if (revoked) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => !revoked && setFailed(true))
    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey])

  return (
    <div className={`flex items-center justify-center bg-lightbox/95 ${className}`}>
      {url && <img src={url} alt={alt} className="max-h-full max-w-full object-contain" />}
      {!url && !failed && <span className="text-xs text-white/50">Loading…</span>}
      {failed && <span className="px-2 text-center text-xs text-white/60">No preview</span>}
    </div>
  )
}
