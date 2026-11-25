export type AgentMode = 'mock' | 'http';

function readMode(raw: string | undefined): AgentMode {
  return raw === 'http' ? 'http' : 'mock';
}

function readBaseUrl(raw: string | undefined): string {
  const value = raw && raw.trim() !== '' ? raw.trim() : '/api';
  return value.replace(/\/+$/, '');
}

export const config = {
  agentMode: readMode(import.meta.env.VITE_AGENT_MODE),
  apiBaseUrl: readBaseUrl(import.meta.env.VITE_API_BASE_URL),
} as const;
