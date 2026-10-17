import { useEffect, useState } from 'react'
import { Check, LoaderCircle, RotateCcw, X } from 'lucide-react'
import { STEPS } from '../lib/usePipeline'
import { formatDuration } from '../lib/format'
import { Button, Panel, PanelHeader } from './ui'

function Elapsed({ since }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(timer)
  }, [])
  return formatDuration(now - since)
}

function StepIcon({ status, number }) {
  const base = 'flex h-6 w-6 shrink-0 items-center justify-center rounded-full'
  if (status === 'done')    return <span className={`${base} bg-success text-surface`}><Check size={14} strokeWidth={3} /></span>
  if (status === 'error')   return <span className={`${base} bg-danger text-surface`}><X size={14} strokeWidth={3} /></span>
  if (status === 'running') return <span className={`${base} text-accent`}><LoaderCircle size={20} className="animate-spin" /></span>
  return <span className={`${base} border border-line font-mono text-[11px] text-faint`}>{number}</span>
}

function stepMeta(state) {
  if (state.status === 'running') {
    return state.progress != null && state.progress < 1
      ? `${Math.round(state.progress * 100)}%`
      : <Elapsed since={state.startedAt} />
  }
  if (state.endedAt) return formatDuration(state.endedAt - state.startedAt)
  return null
}

export default function StepList({ pipeline }) {
  const { steps, error, completed, isDone, retry } = pipeline
  const running = STEPS.find(s => steps[s.id].status === 'running')
  const failed  = STEPS.find(s => s.id === error?.step)
  const total   = STEPS.reduce((sum, s) => sum + (steps[s.id].endedAt - steps[s.id].startedAt || 0), 0)
  const fraction = (completed + (steps.upload.status === 'running' ? steps.upload.progress || 0 : 0)) / STEPS.length

  const summary = isDone ? `Finished in ${formatDuration(total)}`
    : failed ? `Stopped at ${failed.label.toLowerCase()}`
    : running ? `${running.label}…`
    : 'Waiting'

  return (
    <Panel>
      <PanelHeader title="Pipeline" meta={`${completed} of ${STEPS.length}`} />

      <div className="px-4 pt-4">
        <p className="text-sm font-medium" aria-live="polite">{summary}</p>
        <div
          role="progressbar"
          aria-label="Pipeline progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(fraction * 100)}
          className="mt-3 h-1 overflow-hidden rounded-full bg-sunken"
        >
          <div
            className={`h-full rounded-full transition-[width] duration-500 ${isDone ? 'bg-success' : failed ? 'bg-danger' : 'bg-accent'}`}
            style={{ width: `${fraction * 100}%` }}
          />
        </div>
      </div>

      <ol className="mt-2 py-2">
        {STEPS.map((step, i) => {
          const state = steps[step.id]
          return (
            <li key={step.id} className="flex gap-3 px-4 py-2.5">
              <StepIcon status={state.status} number={i + 1} />
              <div className="min-w-0 flex-1 pt-0.5">
                <div className="flex items-baseline gap-2">
                  <span className={`text-sm ${state.status === 'pending' ? 'text-muted' : 'font-medium'}`}>{step.label}</span>
                  <span className="ml-auto font-mono text-xs tabular-nums text-muted">{stepMeta(state)}</span>
                </div>
                {/* a step can report what it actually did, e.g. which voice was used */}
                <p className="mt-0.5 text-xs text-muted">{state.note || step.detail}</p>

                {state.status === 'error' && (
                  <div className="mt-2.5 rounded-md border border-danger/25 bg-danger/[0.06] p-3">
                    <p role="alert" className="text-xs leading-relaxed text-danger">{error.message}</p>
                    <Button size="sm" className="mt-2.5" onClick={retry}>
                      <RotateCcw size={13} /> Retry this step
                    </Button>
                  </div>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </Panel>
  )
}
