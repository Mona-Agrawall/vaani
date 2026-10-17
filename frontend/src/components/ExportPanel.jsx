import { useState } from 'react'
import { Captions, Download } from 'lucide-react'
import { outputUrl, subtitlesUrl } from '../lib/api'
import { LANGUAGES } from '../lib/languages'
import { Button, LanguageSelect, Panel, PanelHeader } from './ui'

export default function ExportPanel({ pipeline }) {
  const { file, lang, videoId, version, redub } = pipeline
  const [next, setNext] = useState(() => LANGUAGES.find(l => l.code !== lang).code)
  const base = `${file.name.replace(/\.mp4$/i, '')}.${lang}`

  return (
    <Panel>
      <PanelHeader title="Export" />
      <div className="space-y-6 p-4">
        <div className="space-y-2">
          <Button
            as="a"
            variant="primary"
            className="w-full"
            href={outputUrl(videoId, version, `${base}.mp4`)}
            download={`${base}.mp4`}
          >
            <Download size={16} /> Download MP4
          </Button>
          <Button
            as="a"
            className="w-full"
            href={subtitlesUrl(videoId, version, 'srt', `${base}.srt`)}
            download={`${base}.srt`}
          >
            <Captions size={16} /> Subtitles (.srt)
          </Button>
        </div>

        <div>
          <label htmlFor="redub-language" className="text-sm font-medium">Dub into another language</label>
          <p className="mt-0.5 text-xs text-muted">Keeps the transcript and re-runs translation, voice and merge.</p>
          <div className="mt-2.5 flex gap-2">
            <LanguageSelect id="redub-language" value={next} onChange={setNext} exclude={lang} className="min-w-0 flex-1" />
            <Button onClick={() => redub(next)}>Re-dub</Button>
          </div>
        </div>
      </div>
    </Panel>
  )
}
