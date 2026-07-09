import glob
import os
import shutil
import subprocess
import sys


def run(cmd: list[str]) -> int:
    print("RUN:", " ".join(cmd), flush=True)
    rc = subprocess.run(cmd, check=False).returncode
    print(f"RC={rc}", flush=True)
    return rc


def build_env() -> dict[str, str]:
    lib_dirs = sorted(glob.glob("/usr/local/lib/python3.12/dist-packages/nvidia/*/lib"))
    env = os.environ.copy()
    if lib_dirs:
        env["LD_LIBRARY_PATH"] = ":".join(
            lib_dirs + [env.get("LD_LIBRARY_PATH", "")]
        ).strip(":")
    return env


def check_vllm_import() -> bool:
    env = build_env()
    rc = subprocess.run(
        [sys.executable, "-c", "import vllm; print(vllm.__version__)"],
        env=env,
        check=False,
    ).returncode
    print(f"IMPORT_RC={rc}", flush=True)
    return rc == 0


def main() -> int:
    uv_bin = shutil.which("uv")
    if uv_bin:
        print("Using uv for remote install", flush=True)
        vllm_rc = run([uv_bin, "pip", "install", "--system", "vllm"])
        runtime_rc = run([uv_bin, "pip", "install", "--system", "nvidia-cuda-runtime"])
        uv_rc = vllm_rc | runtime_rc
        if uv_rc == 0 and check_vllm_import():
            print("INSTALL_OK=1")
            return 0
        print("uv install path failed, falling back to pip", flush=True)
    else:
        print("uv not found, falling back to pip", flush=True)

    run([sys.executable, "-m", "pip", "install", "-U", "pip"])
    run([sys.executable, "-m", "pip", "install", "vllm"])
    run([sys.executable, "-m", "pip", "install", "nvidia-cuda-runtime"])
    print("INSTALL_OK=1" if check_vllm_import() else "INSTALL_OK=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
