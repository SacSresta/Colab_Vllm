from pathlib import Path
import time


def main() -> int:
    log_path = Path("/content/vllm.log")
    position = 0

    print(f"[colab] Tailing {log_path} ...", flush=True)
    while True:
        if log_path.exists():
            with log_path.open("r", errors="ignore") as handle:
                handle.seek(position)
                chunk = handle.read()
                if chunk:
                    print(chunk, end="", flush=True)
                position = handle.tell()
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
