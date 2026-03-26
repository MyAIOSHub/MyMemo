import { Tray, Menu, BrowserWindow, nativeImage, app } from 'electron'
import * as path from 'path'
import { ServiceManager } from './services'

export class TrayManager {
  private tray: Tray | null = null
  private serviceManager: ServiceManager
  private mainWindow: BrowserWindow

  constructor(serviceManager: ServiceManager, mainWindow: BrowserWindow) {
    this.serviceManager = serviceManager
    this.mainWindow = mainWindow
    this.createTray()
  }

  private createTray(): void {
    // Use a simple template image for the tray
    const icon = nativeImage.createEmpty()
    this.tray = new Tray(icon)
    this.tray.setToolTip('EverMemOS Notebook')
    this.updateStatus('starting')

    this.tray.on('click', () => {
      this.mainWindow.show()
      this.mainWindow.focus()
    })
  }

  updateStatus(status: 'starting' | 'running' | 'error'): void {
    if (!this.tray) return

    const statusLabels: Record<string, string> = {
      starting: 'Starting...',
      running: 'Running',
      error: 'Error',
    }

    const statusIcons: Record<string, string> = {
      starting: '🟡',
      running: '🟢',
      error: '🔴',
    }

    const svc = this.serviceManager.status
    const contextMenu = Menu.buildFromTemplate([
      { label: `EverMemOS Notebook — ${statusLabels[status]}`, enabled: false },
      { type: 'separator' },
      { label: `SurrealDB: ${svc.surrealdb}`, enabled: false },
      { label: `API: ${svc.api}`, enabled: false },
      { label: `Memory Hub: ${svc.memoryHub}`, enabled: false },
      { label: `Frontend: ${svc.frontend}`, enabled: false },
      { type: 'separator' },
      {
        label: 'Show Window',
        click: () => {
          this.mainWindow.show()
          this.mainWindow.focus()
        },
      },
      { type: 'separator' },
      {
        label: 'Quit',
        click: () => app.quit(),
      },
    ])

    this.tray.setContextMenu(contextMenu)
    this.tray.setToolTip(`EverMemOS Notebook — ${statusLabels[status]}`)
  }
}
