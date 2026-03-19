export const mailProviderOptions = [
  { label: 'DuckMail', value: 'duckmail' },
  { label: 'Moemail', value: 'moemail' },
  { label: 'Freemail', value: 'freemail' },
  { label: 'GPTMail', value: 'gptmail' },
  { label: 'Cloudflare Mail', value: 'cfmail' },
  { label: 'Sample Mail', value: 'samplemail' },
] as const

export type TempMailProvider = typeof mailProviderOptions[number]['value']

export const defaultMailProvider: TempMailProvider = 'duckmail'
