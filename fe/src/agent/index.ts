import { config } from '../config';
import type { AgentClient } from './client';
import { createAgentCoreClient } from './agentcore';
import { createMockAgentClient } from './mockClient';

/** `VITE_AGENT_MODE` ile mock ya da AgentCore istemcisini seçer (varsayılan: mock). */
export function createAgentClient(): AgentClient {
  return config.agentMode === 'agentcore' ? createAgentCoreClient() : createMockAgentClient();
}
