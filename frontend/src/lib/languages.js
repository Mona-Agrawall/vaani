// Target languages supported by both translation and gTTS voices
export const LANGUAGES = [
  { code: 'hi', name: 'Hindi',      native: 'हिन्दी' },
  { code: 'bn', name: 'Bengali',    native: 'বাংলা' },
  { code: 'ta', name: 'Tamil',      native: 'தமிழ்' },
  { code: 'te', name: 'Telugu',     native: 'తెలుగు' },
  { code: 'mr', name: 'Marathi',    native: 'मराठी' },
  { code: 'gu', name: 'Gujarati',   native: 'ગુજરાતી' },
  { code: 'kn', name: 'Kannada',    native: 'ಕನ್ನಡ' },
  { code: 'ml', name: 'Malayalam',  native: 'മലയാളം' },
  { code: 'ur', name: 'Urdu',       native: 'اردو' },
  { code: 'es', name: 'Spanish',    native: 'Español' },
  { code: 'fr', name: 'French',     native: 'Français' },
  { code: 'de', name: 'German',     native: 'Deutsch' },
  { code: 'it', name: 'Italian',    native: 'Italiano' },
  { code: 'pt', name: 'Portuguese', native: 'Português' },
  { code: 'ru', name: 'Russian',    native: 'Русский' },
  { code: 'ar', name: 'Arabic',     native: 'العربية' },
  { code: 'ja', name: 'Japanese',   native: '日本語' },
  { code: 'ko', name: 'Korean',     native: '한국어' },
]

export const languageName = code => LANGUAGES.find(l => l.code === code)?.name ?? code
