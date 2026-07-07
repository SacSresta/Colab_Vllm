import argparse
import socketserver
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


class ProxyHandler(BaseHTTPRequestHandler):
    upstream_base = ""
    timeout_seconds = 300
    extra_headers = {}
    dns_retry_attempts = 5
    dns_retry_delay_seconds = 1.0

    def do_GET(self):
        self._forward()

    def do_POST(self):
        self._forward()

    def do_PUT(self):
        self._forward()

    def do_PATCH(self):
        self._forward()

    def do_DELETE(self):
        self._forward()

    def do_OPTIONS(self):
        self._forward()

    def do_HEAD(self):
        self._forward()

    def log_message(self, fmt: str, *args):
        # Keep stdout logs concise for long-running local usage.
        return

    def _filtered_headers(self, items: Iterable[tuple[str, str]]) -> dict[str, str]:
        out = {}
        for key, value in items:
            if key.lower() in HOP_BY_HOP_HEADERS or key.lower() == "host":
                continue
            out[key] = value
        return out

    def _is_dns_resolution_error(self, url_err: URLError) -> bool:
        reason = getattr(url_err, "reason", None)
        errno = getattr(reason, "errno", None)
        if errno == -2:
            return True
        text = str(url_err).lower()
        return (
            "name or service not known" in text
            or "temporary failure in name resolution" in text
            or "nodename nor servname provided" in text
        )

    def _send_gateway_error(self, message: str):
        encoded = message.encode("utf-8")
        self.send_response(502)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _forward(self):
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(content_length) if content_length > 0 else None

        target = urljoin(self.upstream_base.rstrip("/") + "/", self.path.lstrip("/"))
        headers = self._filtered_headers(self.headers.items())
        headers.update(self.extra_headers)
        req = Request(target, data=body, headers=headers, method=self.command)

        last_dns_error = None
        for attempt in range(self.dns_retry_attempts):
            try:
                with urlopen(req, timeout=self.timeout_seconds) as resp:
                    self.send_response(resp.status)
                    for key, value in resp.headers.items():
                        if key.lower() in HOP_BY_HOP_HEADERS:
                            continue
                        self.send_header(key, value)
                    self.end_headers()
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                return
            except HTTPError as http_err:
                self.send_response(http_err.code)
                for key, value in http_err.headers.items():
                    if key.lower() in HOP_BY_HOP_HEADERS:
                        continue
                    self.send_header(key, value)
                self.end_headers()
                payload = http_err.read()
                if payload:
                    self.wfile.write(payload)
                return
            except URLError as url_err:
                if self._is_dns_resolution_error(url_err) and attempt + 1 < self.dns_retry_attempts:
                    last_dns_error = url_err
                    time.sleep(self.dns_retry_delay_seconds)
                    continue
                message = f"Upstream unavailable: {url_err}"
                self._send_gateway_error(message)
                return

        if last_dns_error is not None:
            self._send_gateway_error(f"Upstream unavailable: {last_dns_error}")


def main():
    parser = argparse.ArgumentParser(description="Local reverse proxy for remote vLLM.")
    parser.add_argument("--upstream", required=True, help="Upstream base URL.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port.")
    parser.add_argument("--timeout", type=int, default=300, help="Upstream timeout seconds.")
    parser.add_argument(
        "--bearer-token",
        default="",
        help="Optional bearer token added to upstream Authorization header.",
    )
    parser.add_argument(
        "--dns-retries",
        type=int,
        default=5,
        help="Retry count for transient DNS resolution failures.",
    )
    parser.add_argument(
        "--dns-retry-delay",
        type=float,
        default=1.0,
        help="Delay between DNS retry attempts in seconds.",
    )
    args = parser.parse_args()

    ProxyHandler.upstream_base = args.upstream
    ProxyHandler.timeout_seconds = args.timeout
    ProxyHandler.extra_headers = (
        {"Authorization": f"Bearer {args.bearer_token}"} if args.bearer_token else {}
    )
    ProxyHandler.dns_retry_attempts = max(args.dns_retries, 1)
    ProxyHandler.dns_retry_delay_seconds = max(args.dns_retry_delay, 0.0)

    server = ThreadingHTTPServer((args.host, args.port), ProxyHandler)
    print(f"Proxy listening on http://{args.host}:{args.port} -> {args.upstream}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
