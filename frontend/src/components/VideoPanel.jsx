import { useEffect, useRef, useState } from 'react'
import { outputUrl, subtitlesUrl } from '../lib/api'
import { languageName } from '../lib/languages'
import { formatBytes, formatClock } from '../lib/format'
import { stopLoading } from '../lib/media'
import { Panel, PanelHeader } from './ui'

export default function VideoPanel({ pipeline, videoRef, onTimeUpdate }) {
  const { file, previewUrl, isDone, videoId, version, lang, subtitles } = pipeline
  const [choice, setChoice] = useState(null)  // { view, version }: what the viewer picked, and for which result
  const [meta, setMeta] = useState(null)
  const resumeAt = useRef(null)

  // Show each new dubbed result as soon as it exists, and the original while re-dubbing;
  // a manual choice holds until the next result arrives
  const view = !isDone ? 'original' : choice?.version === version ? choice.view : 'dubbed'

  // Each view mounts a new <video>; stop the old one loading (its object URL may be revoked)
  useEffect(() => {
    const video = videoRef.current
    return () => stopLoading(video)
  }, [view, videoRef])

  function switchTo(next) {
    resumeAt.current = videoRef.current?.currentTime ?? null
    setChoice({ view: next, version })
  }

  function handleLoaded(e) {
    const video = e.target
    if (view === 'original') setMeta({ duration: video.duration, width: video.videoWidth, height: video.videoHeight })
    if (resumeAt.current != null) {
      video.currentTime = resumeAt.current
      resumeAt.current = null
    }
  }

  const options = [
    { id: 'original', label: 'Original', enabled: true },
    { id: 'dubbed', label: `Dubbed · ${languageName(lang)}`, enabled: isDone },
  ]

  return (
    <Panel className="overflow-hidden">
      <PanelHeader title="Preview">
        <div className="inline-flex rounded-md bg-sunken p-0.5" role="group" aria-label="Video version">
          {options.map(o => (
            <button
              key={o.id}
              type="button"
              disabled={!o.enabled}
              aria-pressed={view === o.id}
              onClick={() => switchTo(o.id)}
              className={`h-7 rounded px-2.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40
                ${view === o.id ? 'bg-surface text-fg shadow-sm' : 'text-muted hover:text-fg'}`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </PanelHeader>

      <video
        ref={videoRef}
        key={view}
        src={view === 'dubbed' ? outputUrl(videoId, version) : previewUrl}
        controls
        playsInline
        preload="metadata"
        onLoadedMetadata={handleLoaded}
        onTimeUpdate={e => onTimeUpdate(e.target.currentTime)}
        className="block aspect-video w-full bg-black"
      >
        {/* burned-in subtitles are already in the picture; a separate track needs the WebVTT copy */}
        {view === 'dubbed' && subtitles === 'track' && (
          <track
            kind="subtitles"
            src={subtitlesUrl(videoId, version, 'vtt')}
            srcLang={lang}
            label={languageName(lang)}
            default
          />
        )}
      </video>

      <p className="flex flex-wrap gap-x-4 gap-y-1 border-t border-line px-4 py-2.5 font-mono text-xs text-muted">
        <span>{formatBytes(file.size)}</span>
        {meta && <span>{formatClock(meta.duration)}</span>}
        {meta && <span>{meta.width}×{meta.height}</span>}
        <span className="ml-auto">MP4</span>
      </p>
    </Panel>
  )
}
