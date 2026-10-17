/**
 * Stop a <video> that has been removed from the page. A removed video keeps fetching its
 * source, so this must run before that source's object URL is revoked, or every fetch fails.
 * Videos still on the page are left alone (React's development mode runs cleanups early).
 */
export function stopLoading(video) {
  if (!video || video.isConnected) return
  video.removeAttribute('src')
  video.load()
}
