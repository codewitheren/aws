import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createAgentClient } from './agent';
import { App } from './App';
import { ensureDefaultRoute } from './router/router';
import { RunProvider } from './run/RunProvider';
import { applyTheme, initialTheme } from './theme/theme';
import './styles.css';

document.documentElement.classList.add('tk');
applyTheme(initialTheme());
ensureDefaultRoute();

const client = createAgentClient();
const root = document.getElementById('root');
if (!root) throw new Error('#root bulunamadı');

createRoot(root).render(
  <StrictMode>
    <RunProvider client={client}>
      <App />
    </RunProvider>
  </StrictMode>,
);
