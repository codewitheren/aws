export type AgentMode = 'mock' | 'agentcore';

/** `VITE_AGENT_MODE=agentcore`: Cognito girişi + AgentCore Runtime. Varsayılan: tarayıcı içi mock. */
export const config = {
  agentMode: (import.meta.env.VITE_AGENT_MODE === 'agentcore' ? 'agentcore' : 'mock') as AgentMode,
} as const;
