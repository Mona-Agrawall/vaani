import { useRef, useState } from 'react'
import ExportPanel from './ExportPanel'
import ScriptPanel from './ScriptPanel'
import StepList from './StepList'
import VideoPanel from './VideoPanel'

export default function Workspace({ pipeline }) {
  const videoRef = useRef(null)
  const [playhead, setPlayhead] = useState(null)  // seconds; highlights the sentence being played

  function seek(seconds) {
    const video = videoRef.current
    if (!video) return
    video.currentTime = seconds
    video.play().catch(() => {})
    video.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  return (
    <div className="mx-auto grid max-w-[1280px] gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:py-8">
      <div className="min-w-0 space-y-6">
        <VideoPanel pipeline={pipeline} videoRef={videoRef} onTimeUpdate={setPlayhead} />
        <ScriptPanel pipeline={pipeline} playhead={playhead} onSeek={seek} />
      </div>

      {/* On small screens progress comes first, so the current status is always visible */}
      <aside className="order-first space-y-6 lg:sticky lg:top-[88px] lg:order-none lg:self-start">
        <StepList pipeline={pipeline} />
        {pipeline.isDone && <ExportPanel pipeline={pipeline} />}
      </aside>
    </div>
  )
}
