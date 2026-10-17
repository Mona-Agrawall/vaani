import { describe, expect, it, vi } from 'vitest'
import { errorMessage, outputUrl, subtitlesUrl } from './api'
import { formatBytes, formatClock, formatDuration } from './format'
import { LANGUAGES, languageName } from './languages'
import { stopLoading } from './media'
import { STEPS } from './usePipeline'

describe('format', () => {
  it('formats sizes', () => {
    expect(formatBytes(10)).toBe('1 KB')
    expect(formatBytes(300 * 1024)).toBe('300 KB')
    expect(formatBytes(11.3 * 1024 * 1024)).toBe('11.3 MB')
  })

  it('formats step durations', () => {
    expect(formatDuration(4200)).toBe('4.2 s')
    expect(formatDuration(65_000)).toBe('1:05')
    expect(formatDuration(59_600)).toBe('1:00')
  })

  it('formats clock times', () => {
    expect(formatClock(0)).toBe('0:00')
    expect(formatClock(754.4)).toBe('12:34')
    expect(formatClock(NaN)).toBe('–')
  })
})

describe('api', () => {
  it('builds download URLs that change with every result', () => {
    expect(outputUrl('abc', 2)).toBe('/api/download/abc?v=2')
    expect(outputUrl('abc', 2, 'talk.hi.mp4')).toBe('/api/download/abc?v=2&filename=talk.hi.mp4')
    expect(subtitlesUrl('abc', 1, 'vtt')).toBe('/api/subtitles/abc?v=1&format=vtt')
  })

  it('turns errors into one readable message', () => {
    const response = (status, detail) => ({ response: { status, data: { detail } } })
    expect(errorMessage(response(400, 'This video has no audio track.'))).toBe('This video has no audio track.')
    expect(errorMessage(response(422, [{ msg: 'Field required' }, { msg: 'Too long' }]))).toBe('Field required, Too long')
    expect(errorMessage(response(404))).toBe('Request failed (404).')
    expect(errorMessage(response(502))).toMatch(/Could not reach the server/)
    expect(errorMessage(new Error('Network Error'))).toMatch(/Could not reach the server/)
  })
})

describe('languages', () => {
  it('names languages, falling back to the code', () => {
    expect(languageName('hi')).toBe('Hindi')
    expect(languageName('xx')).toBe('xx')
  })

  it('has unique codes', () => {
    expect(new Set(LANGUAGES.map(l => l.code)).size).toBe(LANGUAGES.length)
  })
})

describe('media', () => {
  const video = connected => ({ isConnected: connected, removeAttribute: vi.fn(), load: vi.fn() })

  it('stops a removed video from loading', () => {
    const removed = video(false)
    stopLoading(removed)
    expect(removed.removeAttribute).toHaveBeenCalledWith('src')
    expect(removed.load).toHaveBeenCalled()
  })

  it('leaves a video that is still on the page alone', () => {
    const live = video(true)
    stopLoading(live)
    stopLoading(null)
    expect(live.removeAttribute).not.toHaveBeenCalled()
  })
})

describe('pipeline steps', () => {
  const body = id => STEPS.find(s => s.id === id).body
  const options = { lang: 'ta', voice: 'male', background: 'keep', subtitles: 'track' }

  it('sends each step the options it needs', () => {
    expect(body('separate')(options)).toEqual({ keep_background: true })
    expect(body('translate')(options)).toEqual({ target_lang: 'ta' })
    expect(body('synthesize')(options)).toEqual({ target_lang: 'ta', voice: 'male' })
    expect(body('merge')(options)).toEqual({ burn_subtitles: false })
  })

  it('describes what a step did', () => {
    const describe = id => STEPS.find(s => s.id === id).describe
    expect(describe('separate')({ kept: false })).toBe('Skipped, background not kept')
    expect(describe('synthesize')({ voice: 'Swara, Microsoft neural voice' })).toBe('Swara, Microsoft neural voice')
  })

  it('every step except upload has an endpoint', () => {
    expect(STEPS.filter(s => !s.path).map(s => s.id)).toEqual(['upload'])
  })
})
