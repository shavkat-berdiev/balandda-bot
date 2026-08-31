"""Outbound e-mail via the Plesk mailbox (info@balandda.uz) — SMTP STARTTLS.

Sync smtplib on purpose: callers run it in a thread (asyncio.to_thread) as a
best-effort side task that must never break the payment flow.
"""

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from bot.config import settings


def send_email(to: str, subject: str, text: str,
               attach_name: str | None = None, attach_bytes: bytes | None = None) -> bool:
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        return False
    msg = EmailMessage()
    msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_user))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if attach_name and attach_bytes:
        msg.add_attachment(attach_bytes, maintype="application", subtype="pdf", filename=attach_name)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
        s.ehlo()
        if settings.smtp_port != 465:
            s.starttls()
            s.ehlo()
        s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)
    return True
