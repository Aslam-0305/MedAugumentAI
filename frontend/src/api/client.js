import axios from 'axios'

const key = import.meta.env.VITE_API_KEY
export const http = axios.create({
  baseURL: `${import.meta.env.VITE_API_URL || ''}/api/v1`,
  headers: key ? { 'X-API-Key': key } : {},
})

/** Human-readable message from an API error ({error:{message}}) or a network failure. */
export const errMsg = (e) => e?.response?.data?.error?.message || e?.response?.data?.detail?.[0]?.msg || e?.message || 'Something went wrong'

const get = (url, params) => http.get(url, { params }).then((r) => r.data)
const post = (url, body) => http.post(url, body).then((r) => r.data)

export const api = {
  datasets: () => get('/datasets'),
  dataset: (id) => get(`/datasets/${id}`),
  deleteDataset: (id) => http.delete(`/datasets/${id}`),
  images: (id, params) => get(`/datasets/${id}/images`, params),
  statistics: (id, scope = 'auto') => get(`/datasets/${id}/statistics`, { scope }),
  createSplits: (id, body) => post(`/datasets/${id}/splits`, body),
  createDataset: (form, onUploadProgress) => http.post('/datasets', form, { onUploadProgress }).then((r) => r.data),
  transforms: (modality) => get('/augmentation/transforms', { modality }),
  plan: (body) => post('/augmentation/plan', body),
  createJob: (body) => post('/augmentation/jobs', body),
  jobs: (dataset_id) => get('/jobs', dataset_id ? { dataset_id } : undefined),
  job: (id) => get(`/jobs/${id}`),
  cancelJob: (id) => post(`/jobs/${id}/cancel`),
  deleteJob: (id) => http.delete(`/jobs/${id}`).catch((err) => {
    if (err?.response?.status === 405) return http.post(`/jobs/${id}/delete`)
    throw err
  }),
  results: (id, params) => get(`/jobs/${id}/results`, params),
  reviewSample: (jobId, sampleId, review_status) => http.patch(`/jobs/${jobId}/samples/${sampleId}`, { review_status }).then((r) => r.data),
  exports: () => get('/exports'),
  exportItem: (id) => get(`/exports/${id}`),
  createExport: (body) => post('/exports', body),
}

/** Download through axios so the X-API-Key header is sent. */
export async function downloadExport(id, filename) {
  const res = await http.get(`/exports/${id}/download`, { responseType: 'blob' })
  const url = URL.createObjectURL(res.data)
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  a.click()
  URL.revokeObjectURL(url)
}
