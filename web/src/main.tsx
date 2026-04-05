import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { ensureBrowserGlobalAlias } from './utils/browserCompat'

ensureBrowserGlobalAlias()

ReactDOM.createRoot(document.getElementById('root')!).render(
 <React.StrictMode>
 <App />
 </React.StrictMode>,
)
