"use strict";
const { app, BrowserWindow, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const fs = require("fs");

// Single-instance lock: if a second instance is launched, focus the existing window.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
  process.exit(0);
}

let backendProcess = null;
let frontendProcess = null;
let mainWindow = null;

// ── path helpers ────────────────────────────────────────────────────────────

function resourcePath(...segments) {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, ...segments);
  }
  // Dev mode: paths relative to repo root
  return path.join(__dirname, "..", ...segments);
}

// ── port conflict check ──────────────────────────────────────────────────────

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = require("net").createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close();
      resolve(true);
    });
    server.listen(port, "127.0.0.1");
  });
}

// Find all PIDs listening on a given port and kill them.
function freePort(port) {
  try {
    const out = require("child_process")
      .execSync(`netstat -ano`, { windowsHide: true })
      .toString();
    const pids = new Set();
    for (const line of out.split("\n")) {
      if (line.includes(`:${port} `) && line.includes("LISTENING")) {
        const pid = line.trim().split(/\s+/).pop();
        if (pid && /^\d+$/.test(pid) && pid !== "0") pids.add(pid);
      }
    }
    for (const pid of pids) {
      try {
        require("child_process").execSync(`taskkill /F /T /PID ${pid}`, {
          windowsHide: true,
          stdio: "ignore",
        });
        console.log(`Freed port ${port} by killing PID ${pid}`);
      } catch (_) {}
    }
  } catch (_) {}
}

// ── health polling ───────────────────────────────────────────────────────────

function waitForHttp(url, { maxAttempts = 120, intervalMs = 500 } = {}) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    function attempt() {
      const req = http.get(url, { timeout: 1000 }, (res) => {
        res.resume(); // consume body
        if (res.statusCode < 500) {
          resolve();
        } else {
          retry();
        }
      });
      req.on("error", retry);
      req.on("timeout", () => {
        req.destroy();
        retry();
      });
    }

    function retry() {
      if (++attempts >= maxAttempts) {
        reject(new Error(`Timed out waiting for ${url}`));
      } else {
        setTimeout(attempt, intervalMs);
      }
    }

    attempt();
  });
}

// ── process launchers ────────────────────────────────────────────────────────

function startBackend() {
  const exe = resourcePath("backend", "backend.exe");
  if (!fs.existsSync(exe)) {
    console.warn("backend.exe not found at", exe, "— skipping (dev mode?)");
    return;
  }

  backendProcess = spawn(exe, [], {
    cwd: path.dirname(exe),
    env: {
      ...process.env,
      // Pass user-writable data directory so storage/ and logs/ survive app updates.
      AUTHR_DATA_DIR: app.getPath("userData"),
    },
    windowsHide: true,
    stdio: "ignore",
  });

  backendProcess.on("error", (err) =>
    console.error("Backend process error:", err.message)
  );
  backendProcess.on("exit", (code, sig) =>
    console.log(`Backend exited  code=${code} signal=${sig}`)
  );
}

function startFrontend() {
  const serverJs = resourcePath("frontend", "server.js");
  if (!fs.existsSync(serverJs)) {
    console.warn("frontend server.js not found at", serverJs, "— skipping");
    return;
  }

  // ELECTRON_RUN_AS_NODE=1 makes the Electron binary behave like bare Node.js,
  // letting us run the Next.js standalone server without bundling a second Node.
  frontendProcess = spawn(process.execPath, [serverJs], {
    cwd: resourcePath("frontend"),
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: "1",
      PORT: "3000",
      HOSTNAME: "127.0.0.1",
      // Tell the browser-side JS where the Python API lives.
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000/api",
    },
    windowsHide: true,
    stdio: "ignore",
  });

  frontendProcess.on("error", (err) =>
    console.error("Frontend process error:", err.message)
  );
  frontendProcess.on("exit", (code, sig) =>
    console.log(`Frontend exited  code=${code} signal=${sig}`)
  );
}

// ── window ───────────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 600,
    title: "Auto HR Copilot",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL("http://127.0.0.1:3000");

  // Open target=_blank links in the system browser, not a new Electron window.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ── lifecycle ────────────────────────────────────────────────────────────────

async function main() {
  // Pre-flight: auto-clear any processes occupying the ports we need.
  const [port8000Free, port3000Free] = await Promise.all([
    isPortFree(8000),
    isPortFree(3000),
  ]);

  if (!port8000Free) freePort(8000);
  if (!port3000Free) freePort(3000);

  // Brief pause to let the killed processes release their sockets.
  if (!port8000Free || !port3000Free) {
    await new Promise((r) => setTimeout(r, 1000));
  }

  // Verify ports are now free after the cleanup attempt.
  const [p8free, p3free] = await Promise.all([isPortFree(8000), isPortFree(3000)]);
  if (!p8free || !p3free) {
    const taken = [
      !p8free ? "8000 (API 服务)" : null,
      !p3free ? "3000 (界面服务)" : null,
    ]
      .filter(Boolean)
      .join("、");
    dialog.showErrorBox(
      "端口无法释放",
      `尝试自动释放端口失败，Auto HR 无法启动：\n\n端口 ${taken}\n\n` +
        `请在任务管理器中手动结束相关进程后重试。`
    );
    app.quit();
    return;
  }

  startBackend();
  startFrontend();

  try {
    await Promise.all([
      waitForHttp("http://127.0.0.1:8000/health"),
      waitForHttp("http://127.0.0.1:3000"),
    ]);
  } catch (err) {
    dialog.showErrorBox(
      "启动失败",
      `内部服务未能在限定时间内就绪：\n${err.message}\n\n` +
        `请检查日志目录后重试。\n日志位置：${app.getPath("userData")}\\logs\\`
    );
    app.quit();
    return;
  }

  createWindow();
}

// On Windows, proc.kill() only terminates the launcher; PyInstaller and Node spawn
// child processes that survive. taskkill /F /T kills the whole process tree.
function killProcess(proc) {
  if (!proc || proc.killed) return;
  try {
    if (process.platform === "win32") {
      require("child_process").execSync(
        `taskkill /F /T /PID ${proc.pid}`,
        { windowsHide: true, stdio: "ignore" }
      );
    } else {
      proc.kill("SIGKILL");
    }
  } catch (_) {
    // Process may already be gone — ignore.
  }
}

let cleanedUp = false;
function cleanup() {
  if (cleanedUp) return;
  cleanedUp = true;
  killProcess(backendProcess);
  killProcess(frontendProcess);
  backendProcess = null;
  frontendProcess = null;
}

app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.whenReady().then(main);
app.on("before-quit", cleanup);
app.on("window-all-closed", () => {
  cleanup();
  app.quit();
});
