import axios from 'axios'

// Vite proxies /api to the FastAPI backend (see vite.config.js)
const client = axios.create({ baseURL: '/api' })

export async function uploadVideo(file, onProgress) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post('/upload', form, {
    onUploadProgress: e => e.total && onProgress(e.loaded / e.total),
  })
  return data.video_id
}

export async function runStep(path, body) {
  const { data } = await client.post(path, body)
  return data
}

export async function saveTranslation(videoId, texts) {
  const { data } = await client.put('/translation', { video_id: videoId, texts })
  return data.sentences
}

// `version` changes after every merge so the browser never shows a cached older result
export function outputUrl(videoId, version, filename) {
  const params = new URLSearchParams({ v: version, ...(filename && { filename }) })
  return `/api/download/${videoId}?${params}`
}

export function subtitlesUrl(videoId, version, format, filename) {
  const params = new URLSearchParams({ v: version, format, ...(filename && { filename }) })
  return `/api/subtitles/${videoId}?${params}`
}

export function errorMessage(error) {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(d => d.msg).join(', ')
  if (!error.response || error.response.status >= 502) {
    return 'Could not reach the server. Make sure the backend is running.'
  }
  return `Request failed (${error.response.status}).`
}
