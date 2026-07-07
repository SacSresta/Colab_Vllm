set -euo pipefail

# Reuse the current active session if one exists; otherwise create a new GPU session.
COLAB_GPU="${COLAB_GPU:-T4}"
COLAB_SESSION_NAME="${COLAB_SESSION_NAME:-vllm-colab}"
LOCAL_BIND_HOST="${LOCAL_BIND_HOST:-127.0.0.1}"
LOCAL_BIND_PORT="${LOCAL_BIND_PORT:-8000}"
LOCAL_PROXY_PID_FILE="${LOCAL_PROXY_PID_FILE:-.local-vllm-proxy.pid}"
LOCAL_PROXY_LOG_FILE="${LOCAL_PROXY_LOG_FILE:-local-vllm-proxy.log}"
COLAB_STATE_DIR="${COLAB_STATE_DIR:-$PWD/.colab_state}"
COLAB_INSTALL_TIMEOUT="${COLAB_INSTALL_TIMEOUT:-3600}"
COLAB_BOOT_TIMEOUT="${COLAB_BOOT_TIMEOUT:-300}"
COLAB_TUNNEL_TIMEOUT="${COLAB_TUNNEL_TIMEOUT:-240}"
TUNNEL_READY_TIMEOUT="${TUNNEL_READY_TIMEOUT:-120}"

COLAB_SESSION_ARGS=(--session "$COLAB_SESSION_NAME")
COLAB_CONFIG_PATH="$COLAB_STATE_DIR/sessions.json"
COLAB_HOME_DIR="$COLAB_STATE_DIR/home"
COLAB_CLIENT_OAUTH_CONFIG="$COLAB_HOME_DIR/.colab-cli-oauth-config.json"

mkdir -p "$COLAB_STATE_DIR" "$COLAB_HOME_DIR"

if [ -x ".venv/bin/colab" ]; then
	COLAB_BIN=".venv/bin/colab"
elif command -v colab >/dev/null 2>&1; then
	COLAB_BIN="$(command -v colab)"
else
	echo "Error: colab CLI not found."
	echo "Install dependencies with: uv sync"
	exit 1
fi

if [ -x ".venv/bin/python" ]; then
	python_bin=".venv/bin/python"
else
	python_bin="python3"
fi

run_colab() {
	HOME="$COLAB_HOME_DIR" "$COLAB_BIN" \
		--config "$COLAB_CONFIG_PATH" \
		--client-oauth-config "$COLAB_CLIENT_OAUTH_CONFIG" \
		"$@"
}

if run_colab sessions | grep -q "No active sessions found"; then
	echo "No active Colab session found. Creating ${COLAB_GPU} session named ${COLAB_SESSION_NAME}..."
	run_colab new --gpu "$COLAB_GPU" "${COLAB_SESSION_ARGS[@]}"
else
	echo "Reusing existing Colab session."
fi

# Install vLLM and CUDA runtime bits in Colab.
# Some Colab images run Python 3.12 + torch/cu128 while vLLM wheels require
# CUDA 13 runtime symbols (e.g. libcudart.so.13).
# Install commands are best-effort; readiness is gated by explicit import check.
install_output="$(printf '%s\n' \
	"import glob, os, subprocess, sys" \
	"def run(cmd):" \
	"    print('RUN:', ' '.join(cmd), flush=True)" \
	"    return subprocess.run(cmd, check=False).returncode" \
	"run([sys.executable, '-m', 'pip', 'install', '-U', 'pip'])" \
	"run([sys.executable, '-m', 'pip', 'install', 'vllm'])" \
	"run([sys.executable, '-m', 'pip', 'install', 'nvidia-cuda-runtime-cu13'])" \
	"lib_dirs = sorted(glob.glob('/usr/local/lib/python3.12/dist-packages/nvidia/*/lib'))" \
	"env = os.environ.copy()" \
	"if lib_dirs:" \
	"    env['LD_LIBRARY_PATH'] = ':'.join(lib_dirs + [env.get('LD_LIBRARY_PATH', '')]).strip(':')" \
	"check = subprocess.run([sys.executable, '-c', 'import vllm; print(vllm.__version__)'], env=env, check=False)" \
	"print('INSTALL_OK=1' if check.returncode == 0 else 'INSTALL_OK=0')" \
	| run_colab exec "${COLAB_SESSION_ARGS[@]}" --timeout "$COLAB_INSTALL_TIMEOUT")"

if ! printf '%s\n' "$install_output" | grep -q '^INSTALL_OK=1$'; then
	echo "Error: remote dependency install/import validation failed."
	printf '%s\n' "$install_output"
	exit 1
fi

# Upload all necessary files
for f in .env main.py remote_tunnel.py; do
	run_colab upload "${COLAB_SESSION_ARGS[@]}" "$f" "/content/$f"
done

# Launch remote server
run_colab exec "${COLAB_SESSION_ARGS[@]}" --timeout "$COLAB_BOOT_TIMEOUT" -f main.py

echo "Starting Colab tunnel for vLLM..."
tunnel_output="$(run_colab exec "${COLAB_SESSION_ARGS[@]}" --timeout "$COLAB_TUNNEL_TIMEOUT" -f remote_tunnel.py)"
tunnel_url="$(printf '%s\n' "$tunnel_output" | awk -F= '/^TUNNEL_URL=/{print $2}' | tail -n1)"

if [ -z "$tunnel_url" ]; then
	echo "Error: failed to obtain tunnel URL from remote_tunnel.py"
	echo "Raw output:"
	printf '%s\n' "$tunnel_output"
	exit 1
fi

echo "Waiting for tunnel DNS/HTTP readiness..."
if ! "$python_bin" - "$tunnel_url" "$TUNNEL_READY_TIMEOUT" <<'PY'
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

base_url = sys.argv[1].rstrip('/')
timeout_seconds = int(sys.argv[2])
health_url = f"{base_url}/v1/models"
deadline = time.time() + timeout_seconds
last_error = "unknown"

while time.time() < deadline:
    try:
        with urlopen(health_url, timeout=15) as resp:
            if resp.status < 500:
                print("TUNNEL_READY=1")
                raise SystemExit(0)
    except HTTPError as http_err:
        if http_err.code < 500:
            print("TUNNEL_READY=1")
            raise SystemExit(0)
        last_error = f"HTTP {http_err.code}"
    except URLError as url_err:
        last_error = str(url_err)

    time.sleep(2)

print(f"TUNNEL_READY=0 ({last_error})")
raise SystemExit(1)
PY
then
	echo "Error: tunnel did not become reachable in ${TUNNEL_READY_TIMEOUT}s"
	echo "You can inspect /content/cloudflared-vllm.log in the Colab VM."
	exit 1
fi

if [ -f "$LOCAL_PROXY_PID_FILE" ]; then
	old_pid="$(cat "$LOCAL_PROXY_PID_FILE" || true)"
	if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
		echo "Stopping previous local proxy (PID $old_pid)..."
		kill "$old_pid" || true
	fi
fi

echo "Binding local endpoint on http://${LOCAL_BIND_HOST}:${LOCAL_BIND_PORT} ..."
nohup "$python_bin" local_proxy.py \
	--upstream "$tunnel_url" \
	--host "$LOCAL_BIND_HOST" \
	--port "$LOCAL_BIND_PORT" \
	--dns-retries 8 \
	--dns-retry-delay 1.2 \
	>"$LOCAL_PROXY_LOG_FILE" 2>&1 < /dev/null &
proxy_pid=$!
echo "$proxy_pid" >"$LOCAL_PROXY_PID_FILE"

sleep 1
if ! kill -0 "$proxy_pid" 2>/dev/null; then
	echo "Error: local proxy exited early. Check $LOCAL_PROXY_LOG_FILE"
	exit 1
fi

echo "vLLM remote tunnel URL: $tunnel_url"
echo "Local OpenAI-compatible endpoint: http://${LOCAL_BIND_HOST}:${LOCAL_BIND_PORT}/v1"
echo "Proxy PID file: $LOCAL_PROXY_PID_FILE"
echo "Proxy log file: $LOCAL_PROXY_LOG_FILE"
echo ""
echo "For direct Colab debugging with the same session state used by deploy.sh:"
echo "HOME=\"$COLAB_HOME_DIR\" \"$COLAB_BIN\" --config \"$COLAB_CONFIG_PATH\" --client-oauth-config \"$COLAB_CLIENT_OAUTH_CONFIG\" sessions"
