from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from backend.config import Settings


class EmailSendError(Exception):
    pass


class EmailSender(Protocol):
    def send_login_code(self, to_email: str, code: str, ttl_minutes: int) -> None:
        ...


@dataclass
class NoopEmailSender:
    def send_login_code(self, to_email: str, code: str, ttl_minutes: int) -> None:  # noqa: ARG002
        return


@dataclass
class ResendEmailSender:
    api_key: str
    from_email: str

    def send_login_code(self, to_email: str, code: str, ttl_minutes: int) -> None:
        if not self.api_key or not self.from_email:
            raise EmailSendError("email_not_configured")

        subject = "OneFile 登录验证码"
        html = (
            "<div style='font-family:Inter,Arial,sans-serif;color:#0f172a;line-height:1.6;'>"
            "<h2 style='margin:0 0 12px;font-size:18px;'>OneFile 登录验证码</h2>"
            f"<p style='margin:0 0 8px;'>你的验证码是：</p><p style='font-size:28px;font-weight:700;letter-spacing:4px;margin:0 0 12px;'>{code}</p>"
            f"<p style='margin:0;color:#64748b;'>验证码 {ttl_minutes} 分钟内有效，请勿泄露给他人。</p>"
            "</div>"
        )
        payload = {
            "from": self.from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            if response.status_code >= 400:
                raise EmailSendError("email_send_failed")
        except Exception:
            raise EmailSendError("email_send_failed") from None


def build_email_sender(settings: Settings) -> EmailSender:
    provider = (settings.auth_email_provider or "").lower()
    if provider == "resend":
        return ResendEmailSender(
            api_key=settings.resend_api_key,
            from_email=settings.resend_from_email,
        )
    return NoopEmailSender()
