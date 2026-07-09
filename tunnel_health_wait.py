import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: tunnel_health_wait.py <base_url> <timeout_seconds>")
        return 2

    base_url = sys.argv[1].rstrip("/")
    timeout_seconds = int(sys.argv[2])
    health_url = f"{base_url}/v1/models"
    deadline = time.time() + timeout_seconds
    last_error = "unknown"

    while time.time() < deadline:
        try:
            with urlopen(health_url, timeout=15) as resp:
                if resp.status < 500:
                    print("TUNNEL_READY=1")
                    return 0
        except HTTPError as http_err:
            if http_err.code < 500:
                print("TUNNEL_READY=1")
                return 0
            last_error = f"HTTP {http_err.code}"
        except URLError as url_err:
            last_error = str(url_err)

        time.sleep(2)

    print(f"TUNNEL_READY=0 ({last_error})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
