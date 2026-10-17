import { useLayoutEffect, useRef, useState } from 'react'
import { CircleAlert, Play } from 'lucide-react'
import { languageName } from '../lib/languages'
import { formatClock } from '../lib/format'
import { Button, CopyButton, Panel, PanelHeader } from './ui'

/** A textarea that grows to fit its text, including after the window is resized. */
function AutoTextarea({ value, onChange, ...props }) {
  const ref = useRef(null)
  useLayoutEffect(() => {
    const fit = () => {
      ref.current.style.height = 'auto'
      ref.current.style.height = `${ref.current.scrollHeight}px`
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [value])
  return <textarea ref={ref} rows={1} value={value} onChange={e => onChange(e.target.value)} {...props} />
}

// "Copy original" on wide screens, "Original" on phones where the header is narrow
function CopyLabel({ what }) {
  return (
    <>
      <span className="hidden sm:inline">Copy {what}</span>
      <span className="capitalize sm:hidden">{what}</span>
    </>
  )
}

function Skeleton({ className = '' }) {
  return <div className={`h-3 rounded bg-sunken motion-safe:animate-pulse ${className}`} />
}

/**
 * The transcript and its translation, one row per sentence. The translation can be edited;
 * re-voicing regenerates only the sentences that changed.
 */
export default function ScriptPanel({ pipeline, playhead, onSeek }) {
  const { sentences, steps, lang, isRunning, revoice } = pipeline
  const saved = () => sentences.map(s => s.translated)
  const [drafts, setDrafts]     = useState(saved)
  const [draftsOf, setDraftsOf] = useState(sentences)
  const [saving, setSaving]     = useState(false)
  const [problem, setProblem]   = useState(null)

  // Start again from the saved text whenever the sentences change (new translation, re-dub or
  // re-voice). Adjusting state during render avoids rendering the old drafts first.
  if (draftsOf !== sentences) {
    setDraftsOf(sentences)
    setDrafts(saved())
  }

  const translated = steps.translate.status === 'done'
  const editable   = translated && !isRunning && !saving
  const changed    = drafts.filter((text, i) => text !== sentences[i]?.translated).length
  const active     = playhead == null ? -1 : sentences.findLastIndex(s => s.start <= playhead)

  async function apply() {
    setSaving(true)
    setProblem(null)
    try {
      await revoice(drafts)
    } catch (e) {
      setProblem(e.message)
    } finally {
      setSaving(false)
    }
  }

  const meta = sentences.length
    ? `${sentences.length} sentence${sentences.length === 1 ? '' : 's'} · ${languageName(lang)}`
    : null

  return (
    <Panel className="flex flex-col">
      <PanelHeader title="Script" meta={meta}>
        {sentences.length > 0 && (
          <CopyButton label={<CopyLabel what="original" />} text={sentences.map(s => s.original).join('\n')} />
        )}
        {translated && (
          <CopyButton label={<CopyLabel what="translation" />} text={sentences.map(s => s.translated).join('\n')} />
        )}
      </PanelHeader>

      {sentences.length === 0 ? (
        steps.transcribe.status === 'running' ? (
          <div className="space-y-5 px-4 py-5" aria-label="Transcribing">
            {[0, 1, 2].map(i => (
              <div key={i} className="grid gap-2 md:grid-cols-[48px_1fr_1fr] md:gap-4">
                <Skeleton className="w-10" /><Skeleton /><Skeleton className="w-4/5" />
              </div>
            ))}
          </div>
        ) : (
          <p className="px-4 py-5 text-sm text-faint">
            The script appears here once speech recognition finishes.
          </p>
        )
      ) : (
        <ol className="max-h-[560px] divide-y divide-line overflow-y-auto">
          {sentences.map((sentence, i) => {
            const edited = translated && drafts[i] !== sentence.translated
            return (
              <li
                key={i}
                aria-current={i === active || undefined}
                className={`grid gap-x-4 gap-y-2 px-4 py-3 transition-colors md:grid-cols-[48px_1fr_1fr]
                            ${i === active ? 'bg-accent/[0.06]' : ''}`}
              >
                <button
                  type="button"
                  onClick={() => onSeek(sentence.start)}
                  aria-label={`Play from ${formatClock(sentence.start)}`}
                  className="group flex h-6 items-center gap-1 justify-self-start rounded font-mono text-xs
                             tabular-nums text-muted hover:text-fg"
                >
                  <Play size={10} className="opacity-50 group-hover:opacity-100 group-focus-visible:opacity-100" />
                  {formatClock(sentence.start)}
                </button>

                <p className="text-sm leading-6 text-muted">{sentence.original}</p>

                {translated ? (
                  <AutoTextarea
                    value={drafts[i] ?? ''}
                    onChange={text => setDrafts(d => d.map((old, j) => (j === i ? text : old)))}
                    disabled={!editable}
                    lang={lang}
                    dir="auto"
                    aria-label={`Translation of sentence ${i + 1}`}
                    className={`-mx-2 -my-1 self-start resize-none overflow-hidden rounded-md border bg-transparent px-2 py-1
                                text-[15px] leading-6 text-fg transition-colors disabled:cursor-default
                                ${edited ? 'border-accent/60 bg-accent/[0.04]'
                                         : 'border-transparent enabled:hover:border-line enabled:focus:border-faint'}`}
                  />
                ) : steps.translate.status === 'running' ? (
                  <div className="space-y-2 pt-1.5"><Skeleton /><Skeleton className="w-3/5" /></div>
                ) : (
                  <p className="text-sm leading-6 text-faint">Not translated yet</p>
                )}
              </li>
            )
          })}
        </ol>
      )}

      {translated && (
        <footer className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line px-4 py-3">
          {problem ? (
            <p role="alert" className="flex items-center gap-2 text-xs text-danger">
              <CircleAlert size={14} className="shrink-0" /> {problem}
            </p>
          ) : (
            <p className="text-xs text-muted">
              {changed
                ? `${changed} edited sentence${changed === 1 ? '' : 's'}. Only these are voiced again.`
                : 'Click any translated line to edit it.'}
            </p>
          )}
          {changed > 0 && (
            <div className="ml-auto flex gap-2">
              <Button size="sm" variant="ghost" disabled={saving}
                      onClick={() => { setDrafts(saved()); setProblem(null) }}>
                Discard
              </Button>
              <Button size="sm" variant="primary" disabled={!editable} onClick={apply}>
                {saving ? 'Saving…' : 'Re-voice'}
              </Button>
            </div>
          )}
        </footer>
      )}
    </Panel>
  )
}
