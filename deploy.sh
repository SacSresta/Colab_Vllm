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
STREAM_VLLM_LOGS="${STREAM_VLLM_LOGS:-false}"
COLAB_LOG_STREAM_TIMEOUT="${COLAB_LOG_STREAM_TIMEOUT:-86400}"
COLAB_NEW_RETRIES="${COLAB_NEW_RETRIES:-4}"
COLAB_NEW_RETRY_DELAY="${COLAB_NEW_RETRY_DELAY:-12}"
# Comma-separated accelerator fallback list. Example: "T4,L4"
COLAB_GPU_CANDIDATES="${COLAB_GPU_CANDIDATES:-$COLAB_GPU}"

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

new_session_with_retries() {
	local retries="$1"
	local delay="$2"
	local candidates_csv="$3"
	local attempt
	local gpu

	# Normalize candidate list from CSV to space-delimited.
	local candidates="${candidates_csv//,/ }"

	for gpu in $candidates; do
		echo "Trying accelerator: ${gpu}"
		for ((attempt=1; attempt<=retries; attempt++)); do
			echo "Creating session attempt ${attempt}/${retries} on ${gpu}..."
			set +e
			local output
			output="$(run_colab new --gpu "$gpu" "${COLAB_SESSION_ARGS[@]}" 2>&1)"
			local rc=$?
			set -e

			if [ "$rc" -eq 0 ]; then
				printf '%s\n' "$output"
				return 0
			fi

			printf '%s\n' "$output"

			# Non-retryable entitlement/quota-style accelerator rejection.
			if printf '%s\n' "$output" | grep -qi "Backend rejected accelerator"; then
				echo "Accelerator ${gpu} rejected by backend; moving to next candidate."
				break
			fi

			if [ "$attempt" -lt "$retries" ]; then
				echo "Session create failed. Retrying in ${delay}s..."
				sleep "$delay"
			fi
		done
	done

	return 1
}

if run_colab sessions | grep -q "No active sessions found"; then
	echo "No active Colab session found. Creating session named ${COLAB_SESSION_NAME}..."
	if ! new_session_with_retries "$COLAB_NEW_RETRIES" "$COLAB_NEW_RETRY_DELAY" "$COLAB_GPU_CANDIDATES"; then
		echo "Error: unable to create a Colab session after retries."
		echo "Tried accelerators: ${COLAB_GPU_CANDIDATES}"
		exit 1
	fi
else
	echo "Reusing existing Colab session."
fi

# Install vLLM and CUDA runtime bits in Colab.
# Some Colab images run Python 3.12 + torch/cu128 while vLLM wheels require
# CUDA 13 runtime symbols (e.g. libcudart.so.13).
# Install commands are best-effort; readiness is gated by explicit import check.
install_output="$(run_colab exec "${COLAB_SESSION_ARGS[@]}" --timeout "$COLAB_INSTALL_TIMEOUT" -f remote_install_check.py)"

if ! printf '%s\n' "$install_output" | grep -q '^INSTALL_OK=1$'; then
	echo "Error: remote dependency install/import validation failed."
	printf '%s\n' "$install_output"
	exit 1
fi

# Prepare a reusable shell env for manual Colab console debugging.
env_output="$(run_colab exec "${COLAB_SESSION_ARGS[@]}" --timeout 120 -f remote_prepare_shell_env.py)"
printf '%s\n' "$env_output"

# Upload all necessary files
for f in .env main.py remote_tunnel.py; do
	run_colab upload "${COLAB_SESSION_ARGS[@]}" "$f" "/content/$f"
done

# Launch remote server and enforce readiness before tunnel setup.
boot_output="$(run_colab exec "${COLAB_SESSION_ARGS[@]}" --timeout "$COLAB_BOOT_TIMEOUT" -f main.py 2>&1 || true)"
printf '%s\n' "$boot_output"

if ! printf '%s\n' "$boot_output" | grep -q "vLLM API became reachable on"; then
	echo "Error: remote vLLM startup did not report readiness."
	echo "Skipping tunnel startup because the origin is not healthy."
	if printf '%s\n' "$boot_output" | grep -q "User-specified max_model_len"; then
		echo "Hint: MAX_MODEL_LEN exceeds model limit. For Qwen/Qwen2.5-0.5B-Instruct use MAX_MODEL_LEN=32768."
	fi
	echo "Inspect /content/vllm.log via: bash access.sh console"
	exit 1
fi

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
if ! "$python_bin" tunnel_health_wait.py "$tunnel_url" "$TUNNEL_READY_TIMEOUT"; then
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
echo "Inside Colab console, run: source /content/vllm_env.sh"

if [ "$STREAM_VLLM_LOGS" = "true" ]; then
	echo ""
	echo "Streaming remote vLLM logs from /content/vllm.log (Ctrl-C to stop streaming)."
	run_colab exec "${COLAB_SESSION_ARGS[@]}" --timeout "$COLAB_LOG_STREAM_TIMEOUT" -f remote_tail_vllm_log.py
fi
