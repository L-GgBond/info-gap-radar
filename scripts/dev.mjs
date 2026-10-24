// 一键开发模式：同时拉起 Vite(5173) 与后端，就绪后再启动 Electron 窗口。
// 退出时清理全部子进程，避免残留进程占用端口。
import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const children = [];
let shuttingDown = false;

function killAll() {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    try {
      child.kill();
    } catch {
      // 进程可能已退出
    }
  }
  process.exit(0);
}

process.on("SIGINT", killAll);
process.on("SIGTERM", killAll);
process.on("exit", () => {
  for (const child of children) {
    try {
      child.kill();
    } catch {
      // ignore
    }
  }
});

function waitFor(url, timeoutMs, label) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode) return resolve();
        retry();
      });
      req.on("error", retry);
      req.setTimeout(2000, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        return reject(new Error(`${label} 启动超时`));
      }
      setTimeout(tick, 400);
    };
    tick();
  });
}

const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
const npxCmd = process.platform === "win32" ? "npx.cmd" : "npx";

// 1. 后端：优先 backend/.venv，否则回退系统 Python
const backendDir = path.join(root, "backend");
const venvPython = path.join(backendDir,
  process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python");
const systemPython = process.platform === "win32" ? "python" : "python3";
const backend = spawn(
  fs.existsSync(venvPython) ? venvPython : systemPython,
  ["main.py", "--port", "8765"],
  { cwd: backendDir, stdio: "inherit", shell: process.platform === "win32" }
);
children.push(backend);

// 2. Vite dev server
const vite = spawn(npmCmd, ["run", "dev"], { cwd: root, stdio: "inherit", shell: process.platform === "win32" });
children.push(vite);

try {
  await waitFor("http://127.0.0.1:8765/health", 60000, "后端");
  await waitFor("http://127.0.0.1:5173", 60000, "Vite");
} catch (err) {
  console.error("[electron:dev]", err.message);
  killAll();
}

// 3. Electron 窗口（非 shell 直接跑本地二进制，便于传递退出码）
const electronBin = path.join(root, "node_modules",
  process.platform === "win32" ? ".bin\\electron.cmd" : ".bin/electron");
const electron = spawn(electronBin, ["."], { cwd: root, stdio: "inherit", shell: process.platform === "win32" });
children.push(electron);

electron.on("exit", (code) => {
  shuttingDown = true;
  for (const child of children) {
    if (child !== electron) {
      try {
        child.kill();
      } catch {
        // ignore
      }
    }
  }
  process.exit(code ?? 0);
});
