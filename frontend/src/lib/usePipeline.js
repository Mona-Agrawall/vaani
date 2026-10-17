import { useEffect, useRef, useState } from 'react'
import { errorMessage, runStep, saveTranslation, uploadVideo } from './api'

// `body` builds a step's request fields from the run options ({ lang, voice, background, subtitles });
// `describe` turns its response into a note shown in place of `detail`
export const STEPS = [
  { id: 'upload',     label: 'Upload',              detail: 'Send the video to the server' },
  { id: 'extract',    label: 'Extract audio',       detail: 'FFmpeg, 16 kHz mono',                    path: '/extract-audio' },
  { id: 'separate',   label: 'Separate voice',      detail: 'Demucs, splits speech from background',  path: '/separate',
    body: o => ({ keep_background: o.background === 'keep' }),
    describe: d => (d.kept ? 'Speech and background separated' : 'Skipped, background not kept') },
  { id: 'transcribe', label: 'Transcribe',          detail: 'Whisper, runs on this machine',          path: '/transcribe' },
  { id: 'translate',  label: 'Translate',           detail: 'Google Translate, MyMemory backup',      path: '/translate',
    body: o => ({ target_lang: o.lang }) },
  { id: 'synthesize', label: 'Voice and subtitles', detail: 'Each sentence timed to the original',    path: '/synthesize',
    body: o => ({ target_lang: o.lang, voice: o.voice }),
    describe: d => d.voice },
  { id: 'merge',      label: 'Merge',               detail: 'New audio and subtitles into the video', path: '/merge',
    body: o => ({ burn_subtitles: o.subtitles === 'burn' }) },
]

export const VOICES = [
  { id: 'female', label: 'Female' },
  { id: 'male',   label: 'Male' },
]

export const BACKGROUNDS = [
  { id: 'remove', label: 'Remove', detail: 'Only the new voice. Fastest' },
  { id: 'keep',   label: 'Keep',   detail: 'Music and ambience stay. Slower' },
]

export const SUBTITLE_MODES = [
  { id: 'burn',  label: 'Burned in',      detail: 'Always visible, plays anywhere' },
  { id: 'track', label: 'Separate track', detail: 'Viewers can turn them off' },
]

const REDUB_FROM   = STEPS.findIndex(s => s.id === 'translate')
const REVOICE_FROM = STEPS.findIndex(s => s.id === 'synthesize')

const pendingSteps = (from = 0, current = {}) => Object.fromEntries(
  STEPS.map((s, i) => [s.id, i < from ? current[s.id] : { status: 'pending' }])
)

/** Runs the backend steps in order and tracks status, timing and results for the UI. */
export function usePipeline() {
  const [file, setFile]               = useState(null)
  const [previewUrl, setPreviewUrl]   = useState(null)
  const [options, setOptions]         = useState({})    // { lang, voice, background, subtitles }
  const [steps, setSteps]             = useState(pendingSteps)
  const [error, setError]             = useState(null)  // { step, message }
  const [sentences, setSentences]     = useState([])    // [{ start, end, original, translated }]
  const [videoId, setVideoId]         = useState(null)
  const [version, setVersion]         = useState(0)

  const runId = useRef(0)  // bumped on reset, so a stale run stops updating state

  useEffect(() => () => previewUrl && URL.revokeObjectURL(previewUrl), [previewUrl])

  const update = (id, patch) => setSteps(s => ({ ...s, [id]: { ...s[id], ...patch } }))

  // Translations always line up one to one with the transcript's sentences
  const setTranslated = translated =>
    setSentences(current => current.map((s, i) => ({ ...s, translated: translated[i]?.text ?? '' })))

  async function run(from, { file, options, videoId }) {
    const id = ++runId.current
    const stale = () => id !== runId.current
    setError(null)

    for (const step of STEPS.slice(from)) {
      update(step.id, { status: 'running', startedAt: Date.now(), endedAt: null, progress: null, note: null })
      try {
        let data = {}
        if (step.id === 'upload') {
          videoId = await uploadVideo(file, progress => !stale() && update('upload', { progress }))
          if (!stale()) setVideoId(videoId)
        } else {
          data = await runStep(step.path, { video_id: videoId, ...step.body?.(options) })
          if (stale()) return
          if (step.id === 'transcribe') {
            setSentences(data.sentences.map(s => ({ start: s.start, end: s.end, original: s.text, translated: '' })))
          }
          if (step.id === 'translate') setTranslated(data.sentences)
        }
        if (stale()) return
        update(step.id, { status: 'done', endedAt: Date.now(), note: step.describe?.(data) })
      } catch (e) {
        if (stale()) return
        update(step.id, { status: 'error', endedAt: Date.now() })
        setError({ step: step.id, message: errorMessage(e) })
        return
      }
    }
    setVersion(v => v + 1)
  }

  function start(newFile, newOptions) {
    setFile(newFile)
    setPreviewUrl(URL.createObjectURL(newFile))
    setOptions(newOptions)
    setSteps(pendingSteps())
    setSentences([])
    setVideoId(null)
    run(0, { file: newFile, options: newOptions })
  }

  function retry() {
    const from = STEPS.findIndex(s => s.id === error.step)
    run(from, { file, options, videoId })
  }

  function redub(lang) {
    const newOptions = { ...options, lang }
    setOptions(newOptions)
    setTranslated([])
    setSteps(s => pendingSteps(REDUB_FROM, s))
    run(REDUB_FROM, { file, options: newOptions, videoId })
  }

  /** Save edited translations, then regenerate the voice, subtitles and video.
   *  Throws an Error with a readable message if the edit could not be saved. */
  async function revoice(texts) {
    try {
      setTranslated(await saveTranslation(videoId, texts))
    } catch (e) {
      throw new Error(errorMessage(e))
    }
    setSteps(s => pendingSteps(REVOICE_FROM, s))
    run(REVOICE_FROM, { file, options, videoId })
  }

  function reset() {
    runId.current++
    setFile(null)
    setPreviewUrl(null)
    setOptions({})
    setSteps(pendingSteps())
    setError(null)
    setSentences([])
    setVideoId(null)
  }

  const statuses = STEPS.map(s => steps[s.id].status)

  return {
    file, previewUrl, ...options, steps, error, sentences, videoId, version,
    isRunning: statuses.includes('running'),
    isDone: statuses.every(s => s === 'done'),
    completed: statuses.filter(s => s === 'done').length,
    start, retry, redub, revoice, reset,
  }
}
