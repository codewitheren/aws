/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "mock" (varsayılan) ya da "agentcore". */
  readonly VITE_AGENT_MODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
