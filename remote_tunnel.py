import os
import re
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen


CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-linux-amd64"
)
BIN_PATH = Path("/content/cloudflared")
LOG_PATH = Path("/content/cloudflared-vllm.log")
PID_PATH = Path("/content/cloudflared-vllm.pid")
URL_PATH = Path("/content/cloudflared-vllm.url")
URL_REGEX = re.compile(r"https://[-a-zA-Z0-9]+\.trycloudflare\.com")


def read_port_from_env_file(default: int = 8000) -> int:
    env_path = Path(".env")
    if not env_path.exists():
        return default

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "PORT":
            try:
                return int(value.strip().strip('"').strip("'"))
            except ValueError:
                return default
    return default


def ensure_cloudflared() -> None:
    if BIN_PATH.exists():
        return

    with urlopen(CLOUDFLARED_URL, timeout=60) as response:
        BIN_PATH.write_bytes(response.read())

    mode = BIN_PATH.stat().st_mode
    BIN_PATH.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def stop_previous_tunnel() -> None:
    if not PID_PATH.exists():
        return

    try:
        old_pid = int(PID_PATH.read_text().strip())
    except ValueError:
        PID_PATH.unlink(missing_ok=True)
        return

    try:
        os.kill(old_pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        pass

    PID_PATH.unlink(missing_ok=True)


def start_tunnel(port: int) -> subprocess.Popen:
    LOG_PATH.touch(exist_ok=True)
    with LOG_PATH.open("w", buffering=1) as log_file:
        process = subprocess.Popen(
            [
                str(BIN_PATH),
                "tunnel",
                "--no-autoupdate",
                "--url",
                f"http://127.0.0.1:{port}",
            ],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    PID_PATH.write_text(str(process.pid))
    return process


def read_tunnel_url(process: subprocess.Popen) -> str:
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError(f"cloudflared exited early with code {process.returncode}")

        log_text = LOG_PATH.read_text(errors="ignore")
        matches = URL_REGEX.findall(log_text)
        if matches:
            return matches[-1]
        time.sleep(1)

    raise TimeoutError(
        f"Timed out waiting for tunnel URL. Check {LOG_PATH.as_posix()} for details."
    )


def main() -> int:
    port = read_port_from_env_file()
    try:
        ensure_cloudflared()
        stop_previous_tunnel()
        process = start_tunnel(port)
        url = read_tunnel_url(process)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    URL_PATH.write_text(url + "\n")
    print(f"TUNNEL_URL={url}")
    return 0


if __name__ == "__main__":
    rc = main()
    if rc:
        sys.exit(rc)
