const { app, BrowserWindow, Menu, shell, dialog, ipcMain, Tray, nativeImage } = require('electron');
const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const APP_VERSION = '0.5.3';
const BACKEND_PORT = Number(process.env.SKILLRADAR_API_PORT || 8000);
const FRONTEND_PORT = Number(process.env.SKILLRADAR_WEB_PORT || 3000);

let mainWindow = null;
let tray = null;
let backendProcess = null;
let frontendProcess = null;
let stopping = false;

function nvmNodeBin() {
  const home = process.env.HOME || '';
  const base = path.join(home, '.nvm', 'versions', 'node');
  if (!fs.existsSync(base)) return '';
  const versions = fs.readdirSync(base).filter((n) => n.startsWith('v')).sort();
  if (!versions.length) return '';
  return path.join(base, versions[versions.length - 1], 'bin');
}

function ensurePath() {
  const extras = [];
  const nvmBin = nvmNodeBin();
  if (nvmBin) extras.push(nvmBin);
  extras.push(path.join(__dirname, '..', 'node_modules', '.bin'));
  extras.push('/usr/bin');
  process.env.PATH = `${extras.join(path.delimiter)}${path.delimiter}${process.env.PATH || ''}`;
}

function resolveNpm() {
  const nvmBin = nvmNodeBin();
  const candidates = [
    nvmBin ? path.join(nvmBin, 'npm') : '',
    '/usr/bin/npm',
    'npm',
  ].filter(Boolean);
  for (const cmd of candidates) {
    if (cmd === 'npm' || fs.existsSync(cmd)) return cmd;
  }
  return 'npm';
}

function resolveNode() {
  const nvmBin = nvmNodeBin();
  const candidates = [
    nvmBin ? path.join(nvmBin, 'node') : '',
    '/usr/bin/node',
  ].filter(Boolean);
  for (const cmd of candidates) {
    if (fs.existsSync(cmd)) return cmd;
  }
  return 'node';
}

function isPackaged() {
  return Boolean(app.isPackaged);
}

function repoRoot() {
  const fromElectron = path.join(__dirname, '../..');
  if (fs.existsSync(path.join(fromElectron, 'backend', 'app', 'main.py'))) {
    return fromElectron;
  }
  if (process.resourcesPath && fs.existsSync(path.join(process.resourcesPath, 'backend', 'app', 'main.py'))) {
    return process.resourcesPath;
  }
  return fromElectron;
}

function dataDir() {
  if (isPackaged()) return app.getPath('userData');
  const dir = path.join(repoRoot(), 'data');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function sqliteUrl(dir) {
  const db = path.join(dir, 'skillradar.db');
  return `sqlite:///${db}`;
}

function resolvePython() {
  if (process.env.SKILLRADAR_PYTHON && fs.existsSync(process.env.SKILLRADAR_PYTHON)) {
    return process.env.SKILLRADAR_PYTHON;
  }
  const root = repoRoot();
  const venv = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
  if (fs.existsSync(venv)) return venv;
  const packedVenv = process.platform === 'win32'
    ? path.join(app.getPath('userData'), 'venv', 'Scripts', 'python.exe')
    : path.join(app.getPath('userData'), 'venv', 'bin', 'python');
  if (fs.existsSync(packedVenv)) return packedVenv;
  const home = process.env.HOME || '';
  const candidates = [
    '/usr/bin/python3.12',
    '/usr/bin/python3.11',
    'python3.12',
    'python3.11',
    'python3',
    path.join(home, '.local/bin/python3.12'),
  ];
  for (const cmd of candidates) {
    try {
      execSync(`"${cmd}" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"`, {
        stdio: 'ignore',
      });
      return cmd;
    } catch {
      /* try next */
    }
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function httpOk(url) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: 2500 }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitFor(url, maxMs, label) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    if (await httpOk(url)) return;
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error(`${label} 启动超时（${url}）`);
}

function spawnLogged(command, args, opts) {
  const child = spawn(command, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    ...opts,
  });
  const logFile = path.join(dataDir(), 'electron-child.log');
  const stream = fs.createWriteStream(logFile, { flags: 'a' });
  stream.write(`\n--- ${new Date().toISOString()} ${command} ${args.join(' ')}\n`);
  if (child.stdout) child.stdout.pipe(stream, { end: false });
  if (child.stderr) child.stderr.pipe(stream, { end: false });
  child.on('exit', (code) => {
    stream.write(`exit ${code}\n`);
  });
  return child;
}

async function startBackend() {
  const health = `http://127.0.0.1:${BACKEND_PORT}/api/v1/health`;
  if (await httpOk(health)) return;
  const root = repoRoot();
  const backendDir = fs.existsSync(path.join(root, 'backend', 'app'))
    ? path.join(root, 'backend')
    : path.join(root, 'backend');
  const python = resolvePython();
  const dir = dataDir();
  fs.mkdirSync(path.join(dir, 'clones'), { recursive: true });
  const env = {
    ...process.env,
    PYTHONPATH: backendDir,
    APP_VERSION,
    DATABASE_URL: sqliteUrl(dir),
    CLONE_DIR: path.join(dir, 'clones'),
    CORS_ORIGINS: `http://127.0.0.1:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}`,
  };
  backendProcess = spawnLogged(
    python,
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
    { cwd: backendDir, env },
  );
  await waitFor(health, 45000, '后端 API');
}

function nextStandaloneDir() {
  const packed = path.join(process.resourcesPath || '', 'next');
  if (isPackaged() && fs.existsSync(path.join(packed, 'server.js'))) return packed;
  const local = path.join(__dirname, '..', '.next', 'standalone');
  if (fs.existsSync(path.join(local, 'server.js'))) return local;
  const nested = path.join(__dirname, '..', '.next', 'standalone', 'frontend');
  if (fs.existsSync(path.join(nested, 'server.js'))) return nested;
  return null;
}

async function startFrontend() {
  const web = `http://127.0.0.1:${FRONTEND_PORT}/`;
  if (await httpOk(web)) return;
  const envBase = {
    ...process.env,
    PORT: String(FRONTEND_PORT),
    HOSTNAME: '127.0.0.1',
    BACKEND_URL: `http://127.0.0.1:${BACKEND_PORT}`,
  };
  const standalone = nextStandaloneDir();
  if ((isPackaged() || process.env.SKILLRADAR_USE_STANDALONE === '1') && standalone) {
    frontendProcess = spawnLogged(process.execPath, ['server.js'], {
      cwd: standalone,
      env: { ...envBase, ELECTRON_RUN_AS_NODE: '1' },
    });
    await waitFor(web, 45000, '前端');
    return;
  }
  const frontendDir = path.join(__dirname, '..');
  const nextJs = path.join(frontendDir, 'node_modules', 'next', 'dist', 'bin', 'next');
  const nextShim = path.join(frontendDir, 'node_modules', '.bin', 'next');
  if (!fs.existsSync(nextJs) && !fs.existsSync(nextShim)) {
    throw new Error('未找到 Next.js（frontend/node_modules）。请运行启动脚本以自动安装前端依赖。');
  }
  if (fs.existsSync(nextJs)) {
    frontendProcess = spawnLogged(resolveNode(), [nextJs, 'dev', '-H', '127.0.0.1', '-p', String(FRONTEND_PORT)], {
      cwd: frontendDir,
      env: envBase,
    });
  } else {
    frontendProcess = spawnLogged(nextShim, ['dev', '-H', '127.0.0.1', '-p', String(FRONTEND_PORT)], {
      cwd: frontendDir,
      env: envBase,
    });
  }
  await waitFor(web, 90000, '前端开发服务');
}

function stopChildren() {
  if (stopping) return;
  stopping = true;
  for (const child of [frontendProcess, backendProcess]) {
    if (!child || !child.pid) continue;
    try {
      child.kill('SIGTERM');
    } catch {
      /* already gone */
    }
  }
}

function manualPath() {
  const a = path.join(repoRoot(), '用户手册.md');
  if (fs.existsSync(a)) return a;
  const b = path.join(process.resourcesPath || '', '用户手册.md');
  return fs.existsSync(b) ? b : a;
}

function buildMenu() {
  const web = `http://127.0.0.1:${FRONTEND_PORT}`;
  const send = (route) => {
    if (mainWindow) void mainWindow.loadURL(`${web}${route}`);
  };
  const template = [
    {
      label: 'SkillRadar',
      submenu: [
        { label: '关于', click: () => send('/help') },
        { type: 'separator' },
        { role: 'quit', label: '退出' },
      ],
    },
    {
      label: '转到',
      submenu: [
        { label: '雷达', accelerator: 'CmdOrCtrl+1', click: () => send('/radar') },
        { label: '订阅', accelerator: 'CmdOrCtrl+2', click: () => send('/subscriptions') },
        { label: '设置', accelerator: 'CmdOrCtrl+3', click: () => send('/settings') },
        { label: '登录', click: () => send('/login') },
      ],
    },
    {
      label: '查看',
      submenu: [
        { role: 'reload', label: '重新加载' },
        { role: 'toggleDevTools', label: '开发者工具' },
        { type: 'separator' },
        { role: 'zoomIn', label: '放大' },
        { role: 'zoomOut', label: '缩小' },
        { role: 'resetZoom', label: '默认缩放' },
      ],
    },
    {
      label: '帮助',
      submenu: [
        { label: '应用内手册', click: () => send('/help') },
        {
          label: '打开用户手册文件',
          click: () => {
            void shell.openPath(manualPath());
          },
        },
        {
          label: 'API 文档',
          click: () => {
            void shell.openExternal(`http://127.0.0.1:${BACKEND_PORT}/docs`);
          },
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createTray() {
  const png = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAAM1BMVEUAAAD/////7u7/3Nz/z8//v7//r6//n5//j4//f3//b2//X1//T0//Pz//Ly//Hx//Dw8P/7u4AAADj0oUvAAAAEHRSTlMAECAwQFBgcICPn6+/z9/vX6O99gAAAJBJREFUeNq9k1sOhSAMRXsZ0P7XWokK8jL3f9I0xphg4gdoQ09v2lYqK1gQ0Q6IuQAiZgGI2AAiNoCIXwARXwAiPgFEfAKI+AQQ8Qkg4hNAxCeAiE8AEZ8AIj4BRHwCiPgEEPGjAYj4AxDxByDiD0DEH4CInwAiPgFEfAKI+AQQ8Qkg4gtAxDeAiO8AEd8BIn4ARPwCiPgNEPEnIOI/QMR/gYj/AhH/BSL+C0T8F4j4H6mpF1qkCq6FAAAAAElFTkSuQmCC',
  );
  tray = new Tray(png.resize({ width: 16, height: 16 }));
  tray.setToolTip('SkillRadar');
  tray.setContextMenu(
    Menu.buildFromTemplate([
      {
        label: '打开窗口',
        click: () => {
          if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
          }
        },
      },
      { label: '雷达', click: () => mainWindow && void mainWindow.loadURL(`http://127.0.0.1:${FRONTEND_PORT}/radar`) },
      { type: 'separator' },
      { label: '退出', click: () => app.quit() },
    ]),
  );
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: '#07111f',
    title: `SkillRadar ${APP_VERSION}`,
    show: true,
    autoHideMenuBar: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.once('ready-to-show', () => mainWindow && mainWindow.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    const local = url.startsWith(`http://127.0.0.1:${FRONTEND_PORT}`) || url.startsWith(`http://localhost:${FRONTEND_PORT}`);
    if (!local && !url.startsWith('file:')) {
      event.preventDefault();
      void shell.openExternal(url);
    }
  });
  await mainWindow.loadFile(path.join(__dirname, 'splash.html'));
  try {
    await startBackend();
    await startFrontend();
    await mainWindow.loadURL(`http://127.0.0.1:${FRONTEND_PORT}/`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    let logHint = '';
    try {
      logHint = `\n\n日志: ${path.join(dataDir(), 'electron-child.log')}`;
    } catch {
      /* ignore */
    }
    dialog.showErrorBox('SkillRadar 启动失败', `${msg}${logHint}`);
  }
}

ipcMain.handle('open-external', async (_e, url) => {
  if (typeof url === 'string' && /^https?:\/\//.test(url)) {
    await shell.openExternal(url);
  }
});

ipcMain.handle('open-manual', async () => {
  const p = manualPath();
  if (!fs.existsSync(p)) throw new Error('未找到用户手册');
  await shell.openPath(p);
});

ipcMain.handle('get-paths', async () => ({
  userData: dataDir(),
  db: path.join(dataDir(), 'skillradar.db'),
  clones: path.join(dataDir(), 'clones'),
  version: APP_VERSION,
  packaged: isPackaged(),
}));

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  ensurePath();
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
  app.whenReady().then(async () => {
    ensurePath();
    buildMenu();
    try {
      createTray();
    } catch (err) {
      console.error('tray skipped', err);
    }
    await createWindow();
  });
}

app.on('before-quit', () => stopChildren());
app.on('window-all-closed', () => {
  stopChildren();
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) void createWindow();
});
