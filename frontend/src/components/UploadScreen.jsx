import { useEffect, useRef, useState } from 'react'
import { CircleAlert, FileVideo, Upload, X } from 'lucide-react'
import { BACKGROUNDS, STEPS, SUBTITLE_MODES, VOICES } from '../lib/usePipeline'
import { formatBytes, formatClock } from '../lib/format'
import { stopLoading } from '../lib/media'
import { Button, ChoiceGroup, LanguageSelect, Panel } from './ui'

const MAX_BYTES = 500 * 1024 * 1024

export default function UploadScreen({ onStart }) {
  const [selected, setSelected]     = useState(null)  // { file, url }: the video and a thumbnail URL for it
  const [lang, setLang]             = useState('hi')
  const [voice, setVoice]           = useState('female')
  const [background, setBackground] = useState('remove')
  const [subtitles, setSubtitles]   = useState('burn')
  const [problem, setProblem]       = useState(null)
  const [dragging, setDragging]     = useState(false)
  const thumbnail = useRef(null)

  // Revoke each thumbnail URL once it is replaced or this screen closes
  useEffect(() => () => {
    if (!selected) return
    stopLoading(thumbnail.current)
    URL.revokeObjectURL(selected.url)
  }, [selected])

  function choose(candidate) {
    if (!candidate) return
    if (!candidate.name.toLowerCase().endsWith('.mp4')) return setProblem('Only MP4 files are supported.')
    if (candidate.size > MAX_BYTES) return setProblem(`That file is ${formatBytes(candidate.size)}. The limit is 500 MB.`)
    setProblem(null)
    setSelected({ file: candidate, url: URL.createObjectURL(candidate) })
  }

  const file = selected?.file

  return (
    // DOM order is intro → upload → steps so phones reach the upload panel first;
    // on wide screens the grid places the upload panel in its own right-hand column
    <div className="mx-auto grid max-w-[1120px] gap-10 px-4 py-10 sm:px-6 lg:grid-cols-[1fr_minmax(0,500px)]
                    lg:grid-rows-[auto_1fr] lg:gap-x-20 lg:py-20">
      <div className="max-w-xl lg:col-start-1 lg:row-start-1">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Dub a video into another language
        </h1>
        <p className="mt-4 text-[17px] leading-relaxed text-muted">
          Upload a lecture, interview or talking-head clip. Vaani transcribes the speech,
          translates it, records a new voice track timed to the original, adds subtitles, and
          hands back an MP4.
        </p>
      </div>

      <div className="lg:col-start-2 lg:row-span-2 lg:row-start-1">
        <Panel className="p-5 sm:p-6">
          {selected ? (
            <SelectedFile
              key={selected.url}
              file={selected.file}
              url={selected.url}
              videoRef={thumbnail}
              onClear={() => setSelected(null)}
            />
          ) : (
            <label
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={e => { e.preventDefault(); setDragging(false); choose(e.dataTransfer.files[0]) }}
              className={`flex cursor-pointer flex-col items-center rounded-md border border-dashed px-6 py-12 text-center
                          transition-colors focus-within:ring-2 focus-within:ring-accent/60
                          ${dragging ? 'border-accent bg-accent/5' : 'border-faint/60 hover:border-muted hover:bg-sunken/60'}`}
            >
              <input
                type="file"
                accept="video/mp4"
                className="sr-only"
                onChange={e => { choose(e.target.files[0]); e.target.value = '' }}
              />
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-sunken text-muted">
                <Upload size={18} />
              </span>
              <span className="mt-4 text-sm font-medium">
                {dragging ? 'Drop to add the video' : 'Drag an MP4 here, or click to browse'}
              </span>
              <span className="mt-1 text-xs text-muted">Up to 500 MB</span>
            </label>
          )}

          {problem && (
            <p role="alert" className="mt-3 flex items-center gap-2 text-sm text-danger">
              <CircleAlert size={15} className="shrink-0" /> {problem}
            </p>
          )}

          <label htmlFor="target-language" className="mt-6 block text-sm font-medium">Dub into</label>
          <LanguageSelect id="target-language" value={lang} onChange={setLang} className="mt-2" />

          <ChoiceGroup
            legend="Voice"
            name="voice"
            options={VOICES}
            value={voice}
            onChange={setVoice}
            className="mt-6"
          />

          <ChoiceGroup
            legend="Background sound"
            name="background"
            options={BACKGROUNDS}
            value={background}
            onChange={setBackground}
            className="mt-6"
          />

          <ChoiceGroup
            legend="Subtitles"
            name="subtitles"
            options={SUBTITLE_MODES}
            value={subtitles}
            onChange={setSubtitles}
            className="mt-6"
          />

          <Button
            variant="primary"
            className="mt-6 w-full"
            disabled={!file}
            onClick={() => onStart(file, { lang, voice, background, subtitles })}
          >
            Start dubbing
          </Button>
        </Panel>

        <p className="mt-4 text-xs leading-relaxed text-muted">
          Transcription runs on this machine. The transcript is sent to Google for translation, and
          the translation to Microsoft (or Google as a backup) to generate the voice. Uploaded videos
          are deleted from the server after 24 hours.
        </p>
      </div>

      <div className="max-w-xl lg:col-start-1 lg:row-start-2">
        <h2 className="text-xs font-medium uppercase tracking-wider text-faint">What happens</h2>
        <ol className="mt-3 divide-y divide-line border-y border-line">
          {STEPS.map((step, i) => (
            <li key={step.id} className="flex items-baseline gap-4 py-3">
              <span className="w-5 shrink-0 font-mono text-xs text-faint">{String(i + 1).padStart(2, '0')}</span>
              <span className="text-sm font-medium">{step.label}</span>
              <span className="ml-auto text-right text-sm text-muted">{step.detail}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}

function SelectedFile({ file, url, videoRef, onClear }) {
  const [meta, setMeta] = useState(null)

  return (
    <div className="flex items-center gap-4">
      <div className="relative aspect-video w-28 shrink-0 overflow-hidden rounded bg-sunken">
        <video
          // kept after unmount (React clears refs first), so the parent can stop it loading
          ref={el => el && (videoRef.current = el)}
          src={`${url}#t=1`}
          muted
          preload="metadata"
          className="h-full w-full object-cover"
          onLoadedMetadata={e => setMeta({ duration: e.target.duration, width: e.target.videoWidth, height: e.target.videoHeight })}
        />
        {!meta && <FileVideo size={20} className="absolute inset-0 m-auto text-faint" />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={file.name}>{file.name}</p>
        <p className="mt-1 font-mono text-xs text-muted">
          {formatBytes(file.size)}
          {meta && <> · {formatClock(meta.duration)} · {meta.width}×{meta.height}</>}
        </p>
      </div>
      <Button variant="ghost" size="icon" onClick={onClear} aria-label="Remove video">
        <X size={16} />
      </Button>
    </div>
  )
}
