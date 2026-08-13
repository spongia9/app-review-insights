import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enUS from './locales/en-US.json'
import zhCN from './locales/zh-CN.json'

export const supportedUiLocales = ['zh-CN', 'en-US'] as const
export type UiLocale = (typeof supportedUiLocales)[number]

export const defaultUiLocale: UiLocale = 'zh-CN'
export const uiLocaleStorageKey = 'app-review-insights.ui-locale'

export function resolveUiLocale(language: string | null | undefined): UiLocale {
  return language === 'en-US' ? 'en-US' : defaultUiLocale
}

function readStoredUiLocale(): UiLocale | undefined {
  try {
    const storedLocale = window.localStorage.getItem(uiLocaleStorageKey)
    return supportedUiLocales.find((locale) => locale === storedLocale)
  } catch {
    return undefined
  }
}

const initialLocale = readStoredUiLocale() ?? defaultUiLocale

void i18n.use(initReactI18next).init({
  resources: {
    'zh-CN': { translation: zhCN },
    'en-US': { translation: enUS },
  },
  lng: initialLocale,
  fallbackLng: defaultUiLocale,
  supportedLngs: supportedUiLocales,
  load: 'currentOnly',
  initAsync: false,
  interpolation: {
    escapeValue: false,
  },
  react: {
    useSuspense: false,
  },
})

function syncDocumentLocale(locale: string | null | undefined) {
  document.documentElement.lang = resolveUiLocale(locale)
}

syncDocumentLocale(initialLocale)
i18n.on('languageChanged', syncDocumentLocale)

export async function changeUiLocale(locale: UiLocale) {
  await i18n.changeLanguage(locale)

  try {
    window.localStorage.setItem(uiLocaleStorageKey, locale)
  } catch {
    // The UI still changes when storage is unavailable (for example, in privacy mode).
  }
}

export default i18n
