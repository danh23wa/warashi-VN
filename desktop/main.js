const { app, BrowserWindow, ipcMain, session } = require("electron");
const { spawn } = require("child_process");
const net = require("net");
const path = require("path");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const SERVER_URL = "http://127.0.0.1:12393";
const SERVER_HOST = "127.0.0.1";
const SERVER_PORT = 12393;
let serverProcess;
let mainWindow;

function isPortOpen() {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: SERVER_HOST, port: SERVER_PORT });
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("error", () => resolve(false));
  });
}

async function waitForServer(timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isPortOpen()) return true;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

function startBackend() {
  serverProcess = spawn(
    path.join(PROJECT_ROOT, ".venv", "bin", "python"),
    ["run_server.py"],
    { cwd: PROJECT_ROOT, stdio: "inherit" }
  );
  serverProcess.on("exit", (code) => {
    if (code && !app.isQuitting) {
      console.error(`Warashi backend exited with code ${code}`);
    }
  });
}

async function createWindow() {
  const backendReady = await waitForServer(1500);
  if (!backendReady) startBackend();
  if (!(await waitForServer())) {
    throw new Error("Warashi backend did not become ready.");
  }

  mainWindow = new BrowserWindow({
    width: 460,
    height: 760,
    minWidth: 300,
    minHeight: 420,
    frame: false,
    transparent: true,
    resizable: true,
    alwaysOnTop: true,
    skipTaskbar: false,
    backgroundColor: "#00000000",
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
    },
  });

  mainWindow.setAlwaysOnTop(true, "floating");
  mainWindow.setContentProtection(false);
  await mainWindow.loadURL(`${SERVER_URL}/?desktop=1`);

  await mainWindow.webContents.insertCSS(`
    html, body, #root { background: transparent !important; }
    body { overflow: hidden !important; }
    img[alt="background"],
    [role="dialog"],
    input, textarea,
    button,
    [contenteditable="true"] { display: none !important; }
    canvas {
      position: fixed !important;
      inset: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      z-index: 10 !important;
    }
  `);

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    callback(permission === "media");
  });
  try {
    await createWindow();
  } catch (error) {
    console.error(error);
    app.quit();
  }
});

app.on("before-quit", () => {
  app.isQuitting = true;
  if (serverProcess && !serverProcess.killed) serverProcess.kill("SIGTERM");
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
