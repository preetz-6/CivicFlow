import { useCallback, useEffect, useState } from "react";

/** Display preferences from the top strip: text size and high contrast. */
export type FontSize = "small" | "normal" | "large";

const FONT_KEY = "cf.fontsize";
const CONTRAST_KEY = "cf.contrast";

export function readFontSize(): FontSize {
  const v = localStorage.getItem(FONT_KEY);
  return v === "small" || v === "large" ? v : "normal";
}

export function readHighContrast(): boolean {
  return localStorage.getItem(CONTRAST_KEY) === "high";
}

/** Called once at start-up so the first paint already has the user's settings. */
export function applySavedPrefs() {
  document.documentElement.dataset.fontsize = readFontSize();
  document.documentElement.dataset.contrast = readHighContrast() ? "high" : "normal";
}

export function usePrefs() {
  const [fontSize, setFontSizeState] = useState<FontSize>(readFontSize);
  const [highContrast, setHighContrastState] = useState<boolean>(readHighContrast);

  useEffect(() => {
    document.documentElement.dataset.fontsize = fontSize;
    localStorage.setItem(FONT_KEY, fontSize);
  }, [fontSize]);

  useEffect(() => {
    document.documentElement.dataset.contrast = highContrast ? "high" : "normal";
    localStorage.setItem(CONTRAST_KEY, highContrast ? "high" : "normal");
  }, [highContrast]);

  const toggleContrast = useCallback(() => setHighContrastState((v) => !v), []);

  return { fontSize, setFontSize: setFontSizeState, highContrast, toggleContrast };
}
