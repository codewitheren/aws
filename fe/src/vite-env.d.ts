/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "mock" (varsayılan) ya da "http". */
  readonly VITE_AGENT_MODE?: string;
  /** Agent backend'inin kökü, ör. "/api". */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
