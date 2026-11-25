import { config } from '../config';
import type { AgentClient } from './client';
import { createHttpAgentClient } from './httpClient';
import { createMockAgentClient } from './mockClient';

/** `VITE_AGENT_MODE` ile mock ya da HTTP istemcisini seçer (varsayılan: mock). */
export function createAgentClient(): AgentClient {
  return config.agentMode === 'http' ? createHttpAgentClient(config.apiBaseUrl) : createMockAgentClient();
}
