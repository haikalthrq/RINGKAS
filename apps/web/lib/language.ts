"use client";

import { useEffect, useState } from "react";

export type InterfaceLanguage = "id" | "en";

const storageKey = "ringkas-language";
const languageEvent = "ringkas-language-change";

export function useInterfaceLanguage() {
  const [language, setLanguage] = useState<InterfaceLanguage>("id");

  useEffect(() => {
    const stored = window.localStorage.getItem(storageKey);
    if (stored === "id" || stored === "en") setLanguage(stored);
    else setLanguage(window.navigator.language.toLowerCase().startsWith("id") ? "id" : "en");

    const handleLanguageChange = (event: Event) => {
      const next = (event as CustomEvent<InterfaceLanguage>).detail;
      if (next === "id" || next === "en") setLanguage(next);
    };
    window.addEventListener(languageEvent, handleLanguageChange);
    return () => window.removeEventListener(languageEvent, handleLanguageChange);
  }, []);

  function changeLanguage(next: InterfaceLanguage) {
    setLanguage(next);
    window.localStorage.setItem(storageKey, next);
    window.dispatchEvent(new CustomEvent<InterfaceLanguage>(languageEvent, { detail: next }));
  }

  return [language, changeLanguage] as const;
}
