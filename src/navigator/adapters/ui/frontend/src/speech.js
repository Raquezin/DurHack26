const MS_PER_CHARACTER = 65;
const MIN_SPEECH_MS = 700;

export function speechDurationMs(text) {
  return Math.max(MIN_SPEECH_MS, text.length * MS_PER_CHARACTER);
}
