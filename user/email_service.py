import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def validate_email_config():
        missing = []
        if not getattr(settings, "EMAIL_HOST", ""):
            missing.append("EMAIL_HOST")
        if not getattr(settings, "EMAIL_HOST_USER", ""):
            missing.append("EMAIL_HOST_USER")
        if not getattr(settings, "EMAIL_HOST_PASSWORD", ""):
            missing.append("EMAIL_HOST_PASSWORD")

        if missing:
            raise ImproperlyConfigured(
                f"Missing email configuration: {', '.join(missing)}"
            )

    @classmethod
    def send_email(
        cls,
        *,
        subject,
        from_email,
        to_emails,
        text_body,
        html_body=None,
        fail_silently=False,
    ):
        try:
            cls.validate_email_config()
        except ImproperlyConfigured:
            logger.error("Email configuration is invalid", exc_info=True)
            if fail_silently:
                return 0
            raise

        logger.info("Sending email subject=%s to=%s", subject, to_emails)
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=to_emails,
        )
        if html_body:
            message.attach_alternative(html_body, "text/html")

        result = message.send(fail_silently=fail_silently)
        logger.info("Email send result=%s subject=%s", result, subject)
        return result

    @classmethod
    def send_password_reset_email(cls, *, user, reset_link, fail_silently=False):
        display_name = user.get_full_name() or user.username
        subject = "Yeu cau dat lai mat khau Fotonow"
        from_email = settings.DEFAULT_FROM_EMAIL
        text_body = (
            f"Xin chao {display_name},\n\n"
            "Chung toi da nhan duoc yeu cau dat lai mat khau cho tai khoan Fotonow cua ban.\n\n"
            f"Vui long truy cap lien ket sau de dat lai mat khau:\n{reset_link}\n\n"
            "Neu ban khong yeu cau thao tac nay, vui long bo qua email nay.\n\n"
            "Fotonow Team"
        )
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px;">
            <h2>Yeu cau dat lai mat khau</h2>
            <p>Xin chao {display_name},</p>
            <p>Chung toi da nhan duoc yeu cau dat lai mat khau cho tai khoan Fotonow cua ban.</p>
            <p>
                <a href="{reset_link}" style="display: inline-block; padding: 10px 16px; background: #111827; color: #ffffff; text-decoration: none; border-radius: 6px;">
                    Dat lai mat khau
                </a>
            </p>
            <p>Hoac mo lien ket sau: <br><a href="{reset_link}">{reset_link}</a></p>
            <p>Neu ban khong yeu cau thao tac nay, vui long bo qua email nay.</p>
            <p>Fotonow Team</p>
        </div>
        """

        return cls.send_email(
            subject=subject,
            from_email=from_email,
            to_emails=[user.email],
            text_body=text_body,
            html_body=html_body,
            fail_silently=fail_silently,
        )
