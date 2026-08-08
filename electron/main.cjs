const { app, BrowserWindow } = require("electron");
const { spawn } = require("node:child_process");
const path = require("node:path");
const Store = require("electron-store");

const store = new Store();
let backendProcess;

function startBackend() {
  const port = store.get("backendPort", 8765);
  const packagedBinary = process.platform === "win32" ? "info-gap-backend.exe" : "info-gap-backend";
  const binaryPath = path.join(process.resourcesPath || __dirname, "backend", "dist", packagedBinary);
  const devPath = path.join(__dirname, "..", "backend", "main.py");

  if (app.isPackaged) {
    backendProcess = spawn(binaryPath, ["--port", String(port)], { stdio: "ignore" });
  } else {
    backendProcess = spawn("python3", [devPath, "--port", String(port)], { stdio: "inherit" });
  }

  return port;
}

function createWindow(port) {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 1040,
    minHeight: 700,
    title: "信息差雷达",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs")
    }
  });

  if (app.isPackaged) {
    win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  } else {
    win.loadURL(`http://127.0.0.1:5173?api=http://127.0.0.1:${port}`);
  }
}

app.whenReady().then(() => {
  const port = startBackend();
  createWindow(port);
});

app.on("window-all-closed", () => {
  if (backendProcess) backendProcess.kill();
  if (process.platform !== "darwin") app.quit();
});
