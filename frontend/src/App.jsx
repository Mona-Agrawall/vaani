import { useEffect } from 'react'
import { usePipeline } from './lib/usePipeline'
import TopBar from './components/TopBar'
import UploadScreen from './components/UploadScreen'
import Workspace from './components/Workspace'

export default function App() {
  const pipeline = usePipeline()
  const { file, isRunning, reset } = pipeline

  // Warn before closing the tab while a step is still processing
  useEffect(() => {
    if (!isRunning) return
    const warn = e => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [isRunning])

  function startOver() {
    if (isRunning && !window.confirm('Processing is still running. Discard this video and start over?')) return
    reset()
  }

  return (
    <div className="min-h-screen">
      <TopBar fileName={file?.name} onNew={file ? startOver : null} />
      <main>
        {file ? <Workspace pipeline={pipeline} /> : <UploadScreen onStart={pipeline.start} />}
      </main>
    </div>
  )
}
