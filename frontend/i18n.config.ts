export const locales = ['en', 'hi', 'ta', 'te'] as const
export const defaultLocale = 'en'
export type Locale = (typeof locales)[number]
