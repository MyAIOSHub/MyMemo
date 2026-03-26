import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  getServiceStatus: () => ipcRenderer.invoke('get-service-status'),
  onStatusChange: (callback: (status: unknown) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, status: unknown) => callback(status)
    ipcRenderer.on('service-status-changed', handler)
    // Return cleanup function to prevent listener leaks
    return () => ipcRenderer.removeListener('service-status-changed', handler)
  },
  platform: process.platform,
})
