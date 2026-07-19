"""Run the local FastAPI backend and its ngrok tunnel together.

Configuration comes from the project .env file. The ngrok authtoken is passed
through the child process environment, never as a command-line argument.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent
LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 8000


def _ngrok_executable() -> Path:
    on_path = shutil.which("ngrok")
    if on_path:
        return Path(on_path)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        matches = list(packages.glob("Ngrok.Ngrok_*\\ngrok.exe"))
        if matches:
            return matches[0]

    raise SystemExit(
        "ngrok is not installed or is not on PATH. Install it with: "
        "winget install --id Ngrok.Ngrok --exact"
    )


def _settings() -> tuple[str, str]:
    values = dotenv_values(ROOT / ".env")
    token = (values.get("NGROK_AUTHTOKEN") or "").strip()
    public_url = (values.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")

    if not token:
        raise SystemExit("Set NGROK_AUTHTOKEN in .env before running start.cmd.")
    parsed = urlparse(public_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SystemExit(
            "PUBLIC_BASE_URL must be the public ngrok HTTPS URL, for example "
            "https://example.ngrok-free.app"
        )
    return token, public_url


def _port_is_open() -> bool:
    try:
        with socket.create_connection((LOCAL_HOST, LOCAL_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="validate configuration without starting services"
    )
    args = parser.parse_args()

    token, public_url = _settings()
    ngrok = _ngrok_executable()
    if args.check:
        print(f"ngrok: {ngrok}")
        print(f"public URL: {public_url}")
        print("NGROK_AUTHTOKEN: set")
        return 0

    backend: subprocess.Popen | None = None
    tunnel: subprocess.Popen | None = None
    try:
        if _port_is_open():
            print(f"Backend already running at http://{LOCAL_HOST}:{LOCAL_PORT}")
        else:
            backend = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "backend.main:app",
                    "--reload",
                    "--host",
                    LOCAL_HOST,
                    "--port",
                    str(LOCAL_PORT),
                ],
                cwd=ROOT,
            )
            for _ in range(20):
                if backend.poll() is not None:
                    return backend.returncode or 1
                if _port_is_open():
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("Backend did not start on port 8000.")

        ngrok_env = os.environ.copy()
        ngrok_env["NGROK_AUTHTOKEN"] = token
        tunnel = subprocess.Popen(
            [
                str(ngrok),
                "http",
                "--url",
                public_url,
                str(LOCAL_PORT),
                "--log",
                "stdout",
            ],
            cwd=ROOT,
            env=ngrok_env,
        )
        print(f"Dashboard: http://{LOCAL_HOST}:{LOCAL_PORT}")
        print(f"Public:    {public_url}")
        print("Press Ctrl+C to stop the tunnel and backend.")

        while True:
            if tunnel.poll() is not None:
                return tunnel.returncode or 1
            if backend is not None and backend.poll() is not None:
                return backend.returncode or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        _stop(tunnel)
        _stop(backend)


if __name__ == "__main__":
    raise SystemExit(main())
