import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import kn from "./kn.json";

export type Lang = "en" | "kn";

const KEY = "cf.lang";

function initialLang(): Lang {
  return localStorage.getItem(KEY) === "kn" ? "kn" : "en";
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, kn: { translation: kn } },
  lng: initialLang(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

function applyLang(lng: string) {
  document.documentElement.lang = lng;
  localStorage.setItem(KEY, lng);
}
applyLang(i18n.language);
i18n.on("languageChanged", applyLang);

export default i18n;
