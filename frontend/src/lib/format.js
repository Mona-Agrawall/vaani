export function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// 4.2 s under ten seconds, 1:05 above
export function formatDuration(ms) {
  const seconds = ms / 1000
  if (seconds < 10) return `${seconds.toFixed(1)} s`
  const whole = Math.round(seconds)
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}

export function formatClock(seconds) {
  if (!Number.isFinite(seconds)) return '–'
  const whole = Math.round(seconds)
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}
