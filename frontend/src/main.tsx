import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, HashRouter } from 'react-router';
import App from './App';
import { STATIC_MIRROR } from './lib/mirror';
import './styles/tokens.css';
import './styles/base.css';

// the mirror keeps its routes after '#': any static host then serves every page, deep links and reloads included
const Router = STATIC_MIRROR ? HashRouter : BrowserRouter;

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Router>
      <App />
    </Router>
  </StrictMode>,
);
