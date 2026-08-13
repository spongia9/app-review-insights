import type { ChangeEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { changeUiLocale, resolveUiLocale, type UiLocale } from '../i18n'

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation()
  const currentLocale = resolveUiLocale(i18n.resolvedLanguage ?? i18n.language)

  const handleLanguageChange = (event: ChangeEvent<HTMLSelectElement>) => {
    void changeUiLocale(event.target.value as UiLocale)
  }

  return (
    <label className="flex min-h-11 shrink-0 items-center gap-1.5 rounded-full border border-[#d7e3ee] bg-white px-2.5 py-1 text-[#52677f] transition-colors hover:border-[#a9c1d8] focus-within:border-[#175bd8] focus-within:ring-2 focus-within:ring-[#175bd8]/20">
      <span aria-hidden="true" className="text-sm">
        🌐
      </span>
      <span className="sr-only">{t('language.label')}</span>
      <select
        aria-label={t('language.label')}
        className="cursor-pointer bg-transparent py-0.5 text-xs font-semibold outline-none"
        data-testid="language-switcher"
        onChange={handleLanguageChange}
        value={currentLocale}
      >
        <option value="zh-CN">{t('language.zhCN')}</option>
        <option value="en-US">{t('language.enUS')}</option>
      </select>
    </label>
  )
}
