const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const http = require("node:http");
const Store = require("electron-store");

const store = new Store();
let backendProcess = null;
let backendLog = null;
let quitting = false;

function openBackendLog() {
  const logPath = path.join(app.getPath("userData"), "backend.log");
  try {
    backendLog = fs.createWriteStream(logPath, { flags: "a" });
  } catch {
    backendLog = null;
  }
  return logPath;
}

function logBackendLine(line) {
  if (backendLog) backendLog.write(line);
}

function resolveDevPython() {
  const candidates =
    process.platform === "win32"
      ? [path.join(__dirname, "..", "backend", ".venv", "Scripts", "python.exe")]
      : [path.join(__dirname, "..", "backend", ".venv", "bin", "python")];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return process.platform === "win32" ? "python" : "python3";
}

function startBackend() {
  const port = store.get("backendPort", 8765);
  const logPath = openBackendLog();
  logBackendLine(`\n===== ${new Date().toISOString()} 启动后端 (port ${port}) =====\n`);
  const packagedBinary = process.platform === "win32" ? "info-gap-backend.exe" : "info-gap-backend";
  const binaryPath = path.join(process.resourcesPath || __dirname, "backend", "dist", packagedBinary);
  const devPath = path.join(__dirname, "..", "backend", "main.py");

  if (app.isPackaged) {
    backendProcess = spawn(binaryPath, ["--port", String(port)], {
      // 不再完全吞掉输出：写入日志文件，崩溃时可排查
      stdio: ["ignore", "pipe", "pipe"]
    });
  } else {
    backendProcess = spawn(resolveDevPython(), [devPath, "--port", String(port)], {
      stdio: ["ignore", "pipe", "pipe"]
    });
  }

  backendProcess.stdout?.on("data", (d) => logBackendLine(d.toString()));
  backendProcess.stderr?.on("data", (d) => logBackendLine(d.toString()));
  backendProcess.on("exit", (code, signal) => {
    logBackendLine(`===== 后端退出 code=${code} signal=${signal} =====\n`);
    backendProcess = null;
    // 非主动退出且窗口仍在：弹窗告知，避免"白屏无解释"
    if (!quitting && !app.isQuitting && code !== 0) {
      dialog.showErrorBox(
        "后端服务已退出",
        `信息差雷达的后端进程异常退出（code ${code}）。\n日志文件：${logPath}`
      );
    }
  });

  return port;
}

function createWindow(port) {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 1040,
    minHeight: 700,
    title: "信息差雷达",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs")
    }
  });
  win.once("ready-to-show", () => win.show());

  if (app.isPackaged) {
    win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  } else {
    win.loadURL(`http://127.0.0.1:5173?api=http://127.0.0.1:${port}`);
  }
}

// 轮询后端健康接口，避免桌面端首屏在后端就绪前发起请求导致 500
function waitForBackend(port, retries = 60, delay = 400) {
  return new Promise((resolve, reject) => {
    let attempt = 0;
    const tryOnce = () => {
      const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
        res.resume();
        if (res.statusCode === 200) return resolve();
        retry();
      });
      req.on("error", retry);
      req.setTimeout(1500, () => {
        req.destroy();
        retry();
      });
    };
    function retry() {
      attempt += 1;
      if (attempt >= retries) return reject(new Error("后端服务启动超时"));
      setTimeout(tryOnce, delay);
    }
    tryOnce();
  });
}

app.whenReady().then(async () => {
  const port = startBackend();
  try {
    await waitForBackend(port);
  } catch (err) {
    console.error("[信息差雷达] 后端启动超时：", err.message);
  }
  createWindow(port);
});

app.on("before-quit", () => {
  quitting = true;
});

app.on("window-all-closed", () => {
  quitting = true;
  if (backendProcess) backendProcess.kill();
  if (process.platform !== "darwin") app.quit();
});
