from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import httpx


class NotifyError(Exception):
    pass


def feishu_sign(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def build_feishu_card(title: str, markdown: str, url: str | None = None) -> dict[str, Any]:
    elements: list[dict[str, Any]] = [{"tag": "markdown", "content": markdown[:18000]}]
    if url:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看完整分析"},
                        "url": url,
                        "type": "primary",
                    }
                ],
            }
        )
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title[:80]},
                "template": "blue",
            },
            "elements": elements,
        },
    }


def build_wecom_markdown(markdown: str) -> dict[str, Any]:
    content = markdown.encode("utf-8")[:4096].decode("utf-8", errors="ignore")
    return {"msgtype": "markdown", "markdown": {"content": content}}


class NotificationDispatcher:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client

    def send(self, channel: str, channel_config: dict[str, Any], content: str, title: str) -> None:
        if channel == "feishu":
            self._send_feishu(channel_config, content, title)
            return
        if channel == "wecom":
            self._send_wecom(channel_config, content)
            return
        if channel == "email":
            self._send_email(channel_config, content, title)
            return
        raise NotifyError(f"unsupported channel: {channel}")

    def _client(self) -> httpx.Client:
        if self.client is not None:
            return self.client
        return httpx.Client(timeout=20.0)

    def _post(self, url: str, payload: dict[str, Any]) -> None:
        owns = self.client is None
        client = self._client()
        try:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            try:
                body = resp.json()
            except ValueError:
                body = {}
            if isinstance(body, dict) and int(body.get("code") or body.get("StatusCode") or 0) not in {0}:
                raise NotifyError(f"channel rejected payload: {body}")
        except httpx.HTTPError as exc:
            raise NotifyError(f"webhook post failed: {exc}") from exc
        finally:
            if owns:
                client.close()

    def _send_feishu(self, cfg: dict[str, Any], content: str, title: str) -> None:
        url = (cfg.get("webhook_url") or "").strip()
        if not url.startswith("https://"):
            raise NotifyError("feishu webhook_url must be https")
        payload = build_feishu_card(title, content, cfg.get("report_url"))
        secret = (cfg.get("secret") or "").strip()
        if secret:
            ts = int(time.time())
            payload["timestamp"] = str(ts)
            payload["sign"] = feishu_sign(secret, ts)
        self._post(url, payload)

    def _send_wecom(self, cfg: dict[str, Any], content: str) -> None:
        url = (cfg.get("webhook_url") or "").strip()
        if "qyapi.weixin.qq.com" not in url or "key=" not in url:
            raise NotifyError("wecom webhook_url must contain qyapi.weixin.qq.com and key=")
        self._post(url, build_wecom_markdown(content))

    def _send_email(self, cfg: dict[str, Any], content: str, title: str) -> None:
        import smtplib
        from email.message import EmailMessage

        from app.config import get_settings

        to_addr = (cfg.get("email") or "").strip()
        if "@" not in to_addr:
            raise NotifyError("email address required")
        settings = get_settings()
        host = (cfg.get("smtp_host") or settings.smtp_host or "").strip()
        if not host:
            raise NotifyError("SMTP_HOST is not configured")
        port = int(cfg.get("smtp_port") or settings.smtp_port or 587)
        user = cfg.get("smtp_user") or settings.smtp_user
        password = cfg.get("smtp_password") or settings.smtp_password
        from_addr = (cfg.get("smtp_from") or settings.smtp_from or user or "skillradar@localhost").strip()
        msg = EmailMessage()
        msg["Subject"] = title[:180]
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.set_content(content[:100000])
        try:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                if settings.smtp_starttls:
                    try:
                        smtp.starttls()
                    except smtplib.SMTPException:
                        pass
                if user and password:
                    smtp.login(str(user), str(password))
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            raise NotifyError(f"smtp send failed: {exc}") from exc
