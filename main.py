import glob
import os
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
    load_dotenv()

    model_name = os.getenv("MODEL_NAME")
    hf_token = os.getenv("HF_TOKEN")
    port = int(os.getenv("PORT", "8000"))

    if not model_name:
        print("Error: MODEL_NAME missing in .env")
        sys.exit(1)

    print(f"--- Preparing to serve {model_name} ---")

    cmd = [
        "vllm",
        "serve",
        model_name,
        "--port",
        str(port),
        "--gpu-memory-utilization",
        os.getenv("GPU_MEMORY_UTILIZATION", "0.9"),
        "--max-model-len",
        os.getenv("MAX_MODEL_LEN", "8192"),
    ]

    if hf_token:
        cmd.extend(["--hf-token", hf_token])

    if os.getenv("TRUST_REMOTE_CODE") == "true":
        cmd.append("--trust-remote-code")

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
        print(
            f"Warning: vLLM process is running but port {port} was not reachable "
            f"within {wait_timeout}s."
        )
        print(f"Check {log_path} for model loading progress.")
    else:
        print(f"vLLM API became reachable on 127.0.0.1:{port}")

    print(f"vLLM server started with PID {process.pid}")
    print(f"Logging to {log_path}")


if __name__ == "__main__":
    main()
