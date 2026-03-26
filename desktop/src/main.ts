import { app, BrowserWindow, ipcMain, shell } from 'electron'
import * as path from 'path'
import { ServiceManager } from './services'
import { TrayManager } from './tray'

const FRONTEND_URL = 'http://localhost:3000'

let mainWindow: BrowserWindow | null = null
let serviceManager: ServiceManager | null = null
let trayManager: TrayManager | null = null

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 768,
    title: 'SaySo Notebook',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 16, y: 16 },
  })

  // Open external links in browser
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http') && !url.startsWith(FRONTEND_URL)) {
      shell.openExternal(url)
      return { action: 'deny' }
    }
    return { action: 'allow' }
  })

  return win
}

async function showSplash(win: BrowserWindow): Promise<void> {
  const splashHtml = `
    <html>
    <head>
      <style>
        body {
          margin: 0; display: flex; align-items: center; justify-content: center;
          height: 100vh; background: #1a1a2e; color: #e0e0e0;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
          flex-direction: column; gap: 20px;
        }
        h1 { font-size: 28px; font-weight: 600; color: #f0f0f0; }
        .status { font-size: 14px; color: #888; }
        .spinner {
          width: 32px; height: 32px; border: 3px solid #333;
          border-top-color: #6366f1; border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      </style>
    </head>
    <body>
      <h1>SaySo Notebook</h1>
      <div class="spinner"></div>
      <div class="status">Starting services...</div>
    </body>
    </html>
  `
  win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(splashHtml)}`)
  win.show()
}

async function bootstrap(): Promise<void> {
  mainWindow = createWindow()
  await showSplash(mainWindow)

  // Initialize service manager
  const projectRoot = path.resolve(__dirname, '..', '..')
  serviceManager = new ServiceManager(projectRoot)

  // Register IPC handlers
  ipcMain.handle('get-service-status', () => {
    return serviceManager?.status || {}
  })

  // Initialize tray
  trayManager = new TrayManager(serviceManager, mainWindow)

  // Start services
  try {
    await serviceManager.startAll()
    trayManager.updateStatus('running')
  } catch (err) {
    console.error('Failed to start services:', err)
    trayManager.updateStatus('error')
  }

  // Wait for frontend to be ready
  const ready = await serviceManager.waitForFrontend(60_000)
  if (ready) {
    mainWindow.loadURL(FRONTEND_URL)
  } else {
    const errorHtml = `
      <html><body style="margin:0;display:flex;align-items:center;justify-content:center;height:100vh;background:#1a1a2e;color:#e0e0e0;font-family:system-ui;">
        <div style="text-align:center;max-width:500px">
          <h2>Failed to start core services</h2>
          <p>Please ensure SurrealDB and Python dependencies are installed.</p>
          <p style="font-size:12px;color:#888;margin-top:16px">
            Core: SurrealDB (%SURREALDB%) | API (%API%) | Frontend (%FRONTEND%)<br/>
            Memory Hub (optional): %MEMORYHUB%
          </p>
        </div>
      </body></html>
    `
      .replace('%SURREALDB%', serviceManager.status.surrealdb)
      .replace('%API%', serviceManager.status.api)
      .replace('%FRONTEND%', serviceManager.status.frontend)
      .replace('%MEMORYHUB%', serviceManager.status.memoryHub)

    mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(errorHtml)}`)
  }
}

// App lifecycle
app.whenReady().then(bootstrap)

app.on('window-all-closed', () => {
  mainWindow = null
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show()
  } else {
    bootstrap()
  }
})

app.on('before-quit', async () => {
  if (serviceManager) {
    await serviceManager.stopAll()
  }
})
