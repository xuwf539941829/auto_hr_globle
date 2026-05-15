from __future__ import annotations

import os
import subprocess
from pathlib import Path


class BossLauncherError(RuntimeError):
    pass


_CHROME_PATHS = [
    lambda: Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    lambda: Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    lambda: Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Google" / "Chrome" / "Application" / "chrome.exe",
]

_EDGE_PATHS = [
    lambda: Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    lambda: Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    lambda: Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
]

_BROWSER_DISPLAY_NAMES = {"chrome": "Google Chrome", "edge": "Microsoft Edge"}


class BossLauncher:
    def __init__(self) -> None:
        self.debug_port = 9222
        self.target_url = "https://www.zhipin.com/web/geek/job"

    def launch_login_browser(self, browser_type: str = "auto") -> dict[str, str | int]:
        browser_path, resolved_type = self._find_browser_path(browser_type)
        user_data_dir = self._ensure_user_data_dir(resolved_type)

        args = [
            str(browser_path),
            f"--remote-debugging-port={self.debug_port}",
            f"--user-data-dir={user_data_dir}",
            self.target_url,
        ]

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        try:
            subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=os.name != "nt",
            )
        except OSError as exc:
            raise BossLauncherError(f"启动浏览器失败：{exc}") from exc

        display_name = _BROWSER_DISPLAY_NAMES.get(resolved_type, resolved_type)
        return {
            "status": "launched",
            "browser_type": resolved_type,
            "browser_name": display_name,
            "browser_path": str(browser_path),
            "debug_port": self.debug_port,
            "user_data_dir": str(user_data_dir),
            "target_url": self.target_url,
            "message": f"已启动 {display_name}（带 {self.debug_port} 调试端口），请在新打开的窗口里登录 Boss。",
        }

    @staticmethod
    def _ensure_user_data_dir(browser_type: str) -> Path:
        profile_name = "edge-boss-profile" if browser_type == "edge" else "chrome-boss-profile"
        base_dir = Path.home() / "AppData" / "Local" / "AutoHRCopilot" / profile_name
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    @staticmethod
    def _find_browser_path(browser_type: str) -> tuple[Path, str]:
        if browser_type == "chrome":
            candidates = [("chrome", p) for p in _CHROME_PATHS]
        elif browser_type == "edge":
            candidates = [("edge", p) for p in _EDGE_PATHS]
        elif browser_type == "auto":
            candidates = [("chrome", p) for p in _CHROME_PATHS] + [("edge", p) for p in _EDGE_PATHS]
        else:
            raise BossLauncherError(f"未知浏览器类型：{browser_type}，可选值：chrome、edge、auto")

        for resolved_type, path_fn in candidates:
            path = path_fn()
            if path.exists():
                return path, resolved_type

        if browser_type == "auto":
            raise BossLauncherError("未找到可用的 Chrome 或 Edge，请先安装浏览器。")
        display = _BROWSER_DISPLAY_NAMES.get(browser_type, browser_type)
        raise BossLauncherError(f"未找到 {display}，请先安装。")


boss_launcher = BossLauncher()
