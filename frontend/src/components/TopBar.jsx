import { useState } from 'react'
import { Moon, Plus, Sun } from 'lucide-react'
import { Button } from './ui'

export function Logo() {
  return (
    <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" className="fill-ink" />
      <circle cx="16" cy="16" r="8.5" fill="none" strokeWidth="2.5" className="stroke-on-ink" />
      <circle cx="16" cy="16" r="3" className="fill-accent" />
    </svg>
  )
}

function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    const saved = document.documentElement.dataset.theme
    return saved ? saved === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches
  })

  function toggle() {
    const theme = dark ? 'light' : 'dark'
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('theme', theme) } catch { /* storage blocked: the theme just isn't remembered */ }
    setDark(!dark)
  }

  return (
    <Button variant="ghost" size="icon" onClick={toggle}
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>
      {dark ? <Sun size={16} /> : <Moon size={16} />}
    </Button>
  )
}

export default function TopBar({ fileName, onNew }) {
  return (
    <header className="sticky top-0 z-20 h-14 border-b border-line bg-surface">
      <div className="mx-auto flex h-full max-w-[1280px] items-center gap-3 px-4 sm:px-6">
        <Logo />
        <span className="text-[15px] font-semibold tracking-tight">Vaani</span>
        {fileName && (
          <>
            <span className="text-faint" aria-hidden="true">/</span>
            <span className="min-w-0 truncate text-sm text-muted" title={fileName}>{fileName}</span>
          </>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          {onNew && (
            <Button size="sm" onClick={onNew} aria-label="New video">
              <Plus size={15} />
              <span className="hidden sm:inline">New video</span>
            </Button>
          )}
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
