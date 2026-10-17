import { useState } from 'react'
import { Check, ChevronDown, Copy } from 'lucide-react'
import { LANGUAGES } from '../lib/languages'

const BUTTON_VARIANTS = {
  primary:   'bg-ink text-on-ink hover:bg-ink/85',
  secondary: 'bg-surface text-fg border border-line hover:bg-sunken',
  ghost:     'text-muted hover:text-fg hover:bg-sunken',
}

const BUTTON_SIZES = {
  md: 'h-10 px-4 text-sm gap-2',
  sm: 'h-8 px-3 text-[13px] gap-1.5',
  icon: 'h-8 w-8',
}

export function Button({ as: Tag = 'button', variant = 'secondary', size = 'md', className = '', ...props }) {
  return (
    <Tag
      {...(Tag === 'button' && { type: 'button' })}
      className={`inline-flex items-center justify-center rounded-md font-medium whitespace-nowrap [&_svg]:shrink-0
                  transition-colors disabled:opacity-40 disabled:pointer-events-none
                  ${BUTTON_VARIANTS[variant]} ${BUTTON_SIZES[size]} ${className}`}
      {...props}
    />
  )
}

export function CopyButton({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard permission denied: nothing to show */ }
  }

  return (
    <Button variant="ghost" size="sm" onClick={copy}>
      {copied ? <Check size={14} /> : <Copy size={14} />}
      {copied ? 'Copied' : label}
    </Button>
  )
}

export function LanguageSelect({ value, onChange, id, exclude, className = '' }) {
  return (
    <div className={`relative ${className}`}>
      <select
        id={id}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full h-10 appearance-none rounded-md border border-line bg-surface pl-3 pr-9 text-sm
                   text-fg hover:border-faint transition-colors cursor-pointer"
      >
        {LANGUAGES.filter(l => l.code !== exclude).map(l => (
          <option key={l.code} value={l.code}>{l.name} · {l.native}</option>
        ))}
      </select>
      <ChevronDown size={16} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" />
    </div>
  )
}

/** A row of selectable cards backed by radio inputs. options: [{ id, label, detail? }] */
export function ChoiceGroup({ legend, name, options, value, onChange, className = '' }) {
  return (
    <fieldset className={className}>
      <legend className="text-sm font-medium">{legend}</legend>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {options.map(option => (
          <label
            key={option.id}
            className={`cursor-pointer rounded-md border px-3 py-2.5 transition-colors
                        has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/60
                        ${value === option.id ? 'border-fg bg-sunken/60' : 'border-line hover:border-faint'}`}
          >
            <input
              type="radio"
              name={name}
              value={option.id}
              checked={value === option.id}
              onChange={() => onChange(option.id)}
              className="sr-only"
            />
            <span className="block text-sm font-medium">{option.label}</span>
            {option.detail && <span className="mt-0.5 block text-xs text-muted">{option.detail}</span>}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function Panel({ className = '', children }) {
  return <section className={`rounded-lg border border-line bg-surface ${className}`}>{children}</section>
}

export function PanelHeader({ title, meta, children }) {
  return (
    <header className="flex items-center gap-3 border-b border-line px-4 h-12">
      <h2 className="shrink-0 text-sm font-semibold">{title}</h2>
      {meta && <span className="min-w-0 truncate text-xs text-muted">{meta}</span>}
      <div className="ml-auto flex shrink-0 items-center gap-1">{children}</div>
    </header>
  )
}
