const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('skillradar', {
  desktop: true,
  version: '0.5.3',
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  openManual: () => ipcRenderer.invoke('open-manual'),
  getPaths: () => ipcRenderer.invoke('get-paths'),
});
