/// <reference types="vite/client" />

declare const __BUILD_DATE__: string;

interface ImportMetaEnv {
  readonly VITE_USE_MOCKS?: string;
}
