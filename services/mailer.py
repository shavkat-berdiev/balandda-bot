"""Outbound e-mail via the Plesk mailbox (info@balandda.uz) — SMTP STARTTLS.

Sync smtplib on purpose: callers run it in a thread (asyncio.to_thread).
Raises on any SMTP failure so callers can log WHY a message did not go out;
returns False only when SMTP is not configured at all.
"""

import smtplib
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from bot.config import settings


def send_email(to: str, subject: str, text: str,
               attach_name: str | None = None, attach_bytes: bytes | None = None,
               html: str | None = None, bcc: str | None = None) -> bool:
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        return False
    msg = EmailMessage()
    msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_user))
    msg["To"] = to
    if bcc:
        msg["Bcc"] = bcc
    msg["Reply-To"] = settings.smtp_user
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    domain = settings.smtp_user.split("@")[-1] if "@" in settings.smtp_user else None
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    if attach_name and attach_bytes:
        msg.add_attachment(attach_bytes, maintype="application", subtype="pdf", filename=attach_name)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
        s.ehlo()
        if settings.smtp_port != 465:
            s.starttls()
            s.ehlo()
        s.login(settings.smtp_user, settings.smtp_password)
        refused = s.send_message(msg)
    if refused:
        raise smtplib.SMTPRecipientsRefused(refused)
    return True
