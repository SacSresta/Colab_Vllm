import glob
import os
import shutil
import socket
import subprocess
import sys
import time
from dotenv import load_dotenv


def augment_ld_library_path() -> dict[str, str]:
    env = os.environ.copy()

    # Colab images with Python 3.12 can install vLLM wheels that link against
    # CUDA 13 runtime libs shipped in site-packages/nvidia/cu13/lib.
    lib_dirs = set()
    lib_dirs.update(glob.glob('/usr/local/lib/python3.12/dist-packages/nvidia/*/lib'))
    lib_dirs.update(glob.glob('/usr/local/lib/python3.12/dist-packages/nvidia/*/lib64'))

    if lib_dirs:
        existing = env.get('LD_LIBRARY_PATH', '')
        ordered = sorted(lib_dirs)
        env['LD_LIBRARY_PATH'] = ':'.join(ordered + ([existing] if existing else []))
        print(f"Added {len(ordered)} NVIDIA library paths to LD_LIBRARY_PATH")

    return env


def read_log_tail(path: str, max_chars: int = 4000) -> str:
    try:
        with open(path, "r", errors="ignore") as handle:
            text = handle.read()
            return text[-max_chars:]
    except OSError:
        return ""


def read_root_cause_excerpt(path: str, max_chars: int = 12000) -> str:
    """Return an excerpt that prefers the first traceback/root cause when present."""
    try:
        with open(path, "r", errors="ignore") as handle:
            text = handle.read()
    except OSError:
        return ""

    if not text:
        return ""

    markers = (
        "Traceback (most recent call last):",
        "ImportError:",
        "RuntimeError:",
        "ValueError:",
        "CUDA out of memory",
    )

    start = 0
    for marker in markers:
        idx = text.find(marker)
        if idx != -1:
            start = idx
            break

    excerpt = text[start:]
    return excerpt[:max_chars]


def wait_for_port(host: str, port: int, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(1)
    return False


def main():
    # Colab kernels can retain env vars across exec calls in the same session.
    # Force .env values to override stale values from earlier runs.
    load_dotenv(override=True)

    model_name = os.getenv("MODEL_NAME")
    hf_token = os.getenv("HF_TOKEN")
    port = int(os.getenv("PORT", "8000"))

    if not model_name:
        print("Error: MODEL_NAME missing in .env")
        sys.exit(1)

    print(f"--- Preparing to serve {model_name} ---")

    use_uv = os.getenv("USE_UV_FOR_VLLM", "auto").lower()
    uv_path = shutil.which("uv")
    if use_uv == "true" and not uv_path:
        print("Error: USE_UV_FOR_VLLM=true but 'uv' is not installed.")
        sys.exit(1)

    if use_uv == "true" or (use_uv == "auto" and uv_path):
        cmd = ["uv", "run", "vllm", "serve"]
        print("Using: uv run vllm serve")
    else:
        cmd = ["vllm", "serve"]
        print("Using: vllm serve")

    cmd.extend([
        model_name,
        "--port",
        str(port),
        "--gpu-memory-utilization",
        os.getenv("GPU_MEMORY_UTILIZATION", "0.9"),
        "--max-model-len",
        os.getenv("MAX_MODEL_LEN", "8192"),
        "--max-num-seqs",
        os.getenv("MAX_NUM_SEQS", "1"),
        "--kv-cache-dtype", "auto",
        "--enable-prefix-caching",
    ])

    # KV offloading can help on some setups, but it can also increase startup
    # memory pressure and fail on smaller GPUs. Keep it opt-in.
    if os.getenv("ENABLE_KV_OFFLOADING", "false").lower() == "true":
        cmd.extend([
            "--kv-offloading-backend",
            os.getenv("KV_OFFLOADING_BACKEND", "native"),
            "--kv-offloading-size",
            os.getenv("KV_OFFLOADING_SIZE", "8"),
        ])

    if hf_token:
        cmd.extend(["--hf-token", hf_token])

    if os.getenv("TRUST_REMOTE_CODE") == "true":
        cmd.append("--trust-remote-code")

    # Optional OpenAI tool-calling compatibility flags.
    # Required when clients send tool_choice="auto".
    if os.getenv("ENABLE_AUTO_TOOL_CHOICE", "false").lower() == "true":
        cmd.append("--enable-auto-tool-choice")
        tool_call_parser = os.getenv("TOOL_CALL_PARSER", "").strip()
        if not tool_call_parser:
            print(
                "Error: ENABLE_AUTO_TOOL_CHOICE=true requires TOOL_CALL_PARSER "
                "(example: qwen25 for Qwen2.5 models)."
            )
            sys.exit(1)
        cmd.extend(["--tool-call-parser", tool_call_parser])

    print("Launching vLLM server...")
    log_path = os.getenv("VLLM_LOG_FILE", "vllm.log")
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    launch_env = augment_ld_library_path()

    with open(log_path, "a", buffering=1) as log_file:
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=launch_env,
        )

    early_exit_window = int(os.getenv("VLLM_EARLY_EXIT_WINDOW", "8"))
    for _ in range(early_exit_window):
        time.sleep(1)
        if process.poll() is not None:
            print(f"Error: vLLM exited early with code {process.returncode}")
            print(f"See {log_path} for the full log.")
            sys.exit(process.returncode or 1)

    wait_timeout = int(os.getenv("VLLM_PORT_WAIT_TIMEOUT", "180"))
    if not wait_for_port("127.0.0.1", port, wait_timeout):
        allow_unready = os.getenv("ALLOW_UNREADY_STARTUP", "false").lower() == "true"
        log_tail = read_log_tail(log_path)
        root_excerpt = read_root_cause_excerpt(
            log_path, int(os.getenv("VLLM_LOG_CONTEXT_CHARS", "12000"))
        )
        if process.poll() is not None:
            print(f"Error: vLLM exited with code {process.returncode} before becoming ready.")
            if "User-specified max_model_len" in log_tail:
                print(
                    "Hint: MAX_MODEL_LEN is above the model's supported context window. "
                    "Lower MAX_MODEL_LEN (for this model, likely 32768) or explicitly set "
                    "VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 only if you accept the risk."
                )
            if "CUDA error: out of memory" in (root_excerpt or log_tail):
                print(
                    "Hint: CUDA OOM during startup. Try reducing MAX_MODEL_LEN "
                    "(e.g. 8192 or 4096), reducing GPU_MEMORY_UTILIZATION "
                    "(e.g. 0.75), and keep ENABLE_KV_OFFLOADING=false."
                )
            if root_excerpt:
                print("\n--- vLLM root-cause excerpt ---")
                print(root_excerpt)
            elif log_tail:
                print("\n--- vLLM log tail ---")
                print(log_tail)
            sys.exit(process.returncode or 1)

        message = (
            f"vLLM process is still running but port {port} was not reachable within "
            f"{wait_timeout}s."
        )
        if allow_unready:
            print(f"Warning: {message}")
            print(f"Continuing because ALLOW_UNREADY_STARTUP=true. Check {log_path}.")
        else:
            print(f"Error: {message}")
            if "User-specified max_model_len" in log_tail:
                print(
                    "Hint: MAX_MODEL_LEN appears too high for this model. "
                    "Try MAX_MODEL_LEN=32768 for Qwen/Qwen2.5-0.5B-Instruct."
                )
            if "CUDA error: out of memory" in (root_excerpt or log_tail):
                print(
                    "Hint: CUDA OOM during startup. Try lowering MAX_MODEL_LEN, "
                    "lowering GPU_MEMORY_UTILIZATION, or disabling KV offloading."
                )
            if root_excerpt:
                print("\n--- vLLM root-cause excerpt ---")
                print(root_excerpt)
            elif log_tail:
                print("\n--- vLLM log tail ---")
                print(log_tail)
            print("Set ALLOW_UNREADY_STARTUP=true only if you want deploy to continue anyway.")
            sys.exit(1)
    else:
        print(f"vLLM API became reachable on 127.0.0.1:{port}")

    print(f"vLLM server started with PID {process.pid}")
    print(f"Logging to {log_path}")


if __name__ == "__main__":
    main()
