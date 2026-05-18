#!/usr/bin/env python3
"""HTTP webhook endpoint that triggers the laumy Git deploy service.

The endpoint accepts either:
- GitHub native webhooks signed with X-Hub-Signature-256.
- GitHub Actions curl requests using Authorization: Bearer <secret>.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


HOST = os.environ.get("WEBHOOK_HOST", "127.0.0.1")
PORT = int(os.environ.get("WEBHOOK_PORT", "8789"))
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/deploy-hook")
HEALTH_PATH = os.environ.get("WEBHOOK_HEALTH_PATH", f"{WEBHOOK_PATH}/healthz")
SECRET = (
    os.environ.get("WEBHOOK_SECRET")
    or os.environ.get("DEPLOY_WEBHOOK_SECRET")
    or os.environ.get("WEBHOOK_TOKEN")
    or ""
)
DEPLOY_SERVICE = os.environ.get("DEPLOY_SERVICE", "laumy-git-deploy.service")
MAX_BODY_BYTES = int(os.environ.get("WEBHOOK_MAX_BODY_BYTES", "262144"))


def csv_set(name: str) -> set[str]:
    raw = os.environ.get(name, "")
    return {item.strip() for item in raw.split(",") if item.strip()}


ALLOWED_REPOSITORIES = csv_set("ALLOWED_REPOSITORIES")
ALLOWED_REFS = csv_set("ALLOWED_REFS")


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def verify_bearer(headers: Any) -> bool:
    expected = f"Bearer {SECRET}"
    provided = headers.get("Authorization", "")
    return bool(SECRET) and hmac.compare_digest(provided, expected)


def verify_github_signature(headers: Any, body: bytes) -> bool:
    signature = headers.get("X-Hub-Signature-256", "")
    if not SECRET or not signature.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def get_repo_name(payload: dict[str, Any]) -> str:
    repo = payload.get("repository")
    if isinstance(repo, dict):
        return str(repo.get("full_name") or "")
    if isinstance(repo, str):
        return repo
    return ""


def get_ref(payload: dict[str, Any]) -> str:
    ref = payload.get("ref")
    if isinstance(ref, str):
        return ref
    return ""


def is_allowed(value: str, allowed: set[str]) -> bool:
    return not allowed or value in allowed


def trigger_deploy() -> None:
    subprocess.run(
        ["systemctl", "start", "--no-block", DEPLOY_SERVICE],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class DeployWebhookHandler(BaseHTTPRequestHandler):
    server_version = "LaumyDeployWebhook/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == HEALTH_PATH:
            json_response(self, 200, {"ok": True, "service": DEPLOY_SERVICE})
            return
        json_response(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != WEBHOOK_PATH:
            json_response(self, 404, {"ok": False, "error": "not found"})
            return

        length_header = self.headers.get("Content-Length", "0")
        try:
            length = int(length_header)
        except ValueError:
            json_response(self, 400, {"ok": False, "error": "invalid content length"})
            return

        if length > MAX_BODY_BYTES:
            json_response(self, 413, {"ok": False, "error": "payload too large"})
            return

        body = self.rfile.read(length)
        if not (verify_bearer(self.headers) or verify_github_signature(self.headers, body)):
            logging.warning("Rejected webhook with invalid signature/token")
            json_response(self, 401, {"ok": False, "error": "unauthorized"})
            return

        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            json_response(self, 400, {"ok": False, "error": "invalid json"})
            return

        if not isinstance(payload, dict):
            json_response(self, 400, {"ok": False, "error": "payload must be an object"})
            return

        event = self.headers.get("X-GitHub-Event", "")
        repo = get_repo_name(payload)
        ref = get_ref(payload)

        if event == "ping":
            logging.info("Accepted GitHub ping for repo=%s", repo or "-")
            json_response(self, 200, {"ok": True, "event": "ping"})
            return

        if repo and not is_allowed(repo, ALLOWED_REPOSITORIES):
            logging.warning("Rejected webhook from unexpected repo=%s", repo)
            json_response(self, 403, {"ok": False, "error": "repository not allowed"})
            return

        if ref and not is_allowed(ref, ALLOWED_REFS):
            logging.info("Ignored webhook for repo=%s ref=%s", repo or "-", ref)
            json_response(self, 202, {"ok": True, "triggered": False, "reason": "ref ignored"})
            return

        try:
            trigger_deploy()
        except subprocess.CalledProcessError as exc:
            logging.error("Failed to trigger %s: %s", DEPLOY_SERVICE, exc.stderr.strip())
            json_response(self, 500, {"ok": False, "error": "failed to trigger deploy"})
            return

        logging.info("Triggered %s from event=%s repo=%s ref=%s", DEPLOY_SERVICE, event or "-", repo or "-", ref or "-")
        json_response(self, 202, {"ok": True, "triggered": True})


def main() -> None:
    if not SECRET:
        raise SystemExit("WEBHOOK_SECRET is required")

    server = ThreadingHTTPServer((HOST, PORT), DeployWebhookHandler)
    logging.info("Listening on http://%s:%s%s", HOST, PORT, WEBHOOK_PATH)
    server.serve_forever()


if __name__ == "__main__":
    main()
