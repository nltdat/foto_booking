"""Management command to test email sending."""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from user.email_service import EmailService
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.conf import settings

User = get_user_model()


class Command(BaseCommand):
    help = "Test email sending functionality"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            default="test@example.com",
            help="Email address to send to (default: test@example.com)",
        )
        parser.add_argument(
            "--type",
            type=str,
            choices=["simple", "password-reset"],
            default="simple",
            help="Type of email to send (default: simple)",
        )

    def handle(self, *args, **options):
        email = options["email"].strip()
        email_type = options["type"]

        self.stdout.write(f"Testing email send to: {email}")
        self.stdout.write(f"Email type: {email_type}")
        self.stdout.write("")

        # Validate config first
        try:
            self.stdout.write("Validating email configuration...")
            EmailService.validate_email_config()
            self.stdout.write(self.style.SUCCESS("✓ Email config is valid"))
        except Exception as e:
            raise CommandError(f"Email config invalid: {e}")

        # Send test email
        try:
            if email_type == "simple":
                self.stdout.write("Sending simple test email...")
                result = EmailService.send_email(
                    subject="[Fotonow Test] Kiểm Tra Email",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to_emails=[email],
                    text_body="Đây là email kiểm tra từ Fotonow.\n\nNếu bạn nhận được email này, hệ thống gửi email đang hoạt động bình thường.",
                    html_body="""
                    <div style="font-family: Arial, sans-serif; max-width: 600px;">
                        <h2>Kiểm Tra Email Fotonow</h2>
                        <p>Xin chào,</p>
                        <p>Đây là email kiểm tra từ Fotonow.</p>
                        <p style="background-color: #f0f0f0; padding: 15px; border-radius: 5px;">
                            <strong style="color: green;">✓</strong> Nếu bạn nhận được email này, hệ thống gửi email đang hoạt động bình thường.
                        </p>
                        <p>Thời gian kiểm tra: <code>{}</code></p>
                        <p>---<br>Fotonow Team</p>
                    </div>
                    """.format(__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )

            elif email_type == "password-reset":
                # Try to find or create a test user
                user = User.objects.filter(email__iexact=email).first()
                if not user:
                    self.stdout.write(self.style.WARNING(f"⚠ User with email {email} not found"))
                    self.stdout.write("Creating temporary test user...")
                    user = User.objects.create_user(
                        username=f"testuser_{__import__('uuid').uuid4().hex[:8]}",
                        email=email,
                        password="TempPass123!",
                    )
                    self.stdout.write(f"  Created user: {user.username}")

                self.stdout.write("Sending password reset email...")
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                reset_link = f"{settings.FRONTEND_RESET_PASSWORD_URL}?uid={uid}&token={token}"
                
                result = EmailService.send_password_reset_email(
                    user=user,
                    reset_link=reset_link,
                )

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"✓ Email sent successfully! ({result} email)"))
            self.stdout.write(f"  To: {email}")
            self.stdout.write(f"  From: {settings.DEFAULT_FROM_EMAIL}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Failed to send email: {e}"))
            raise CommandError(str(e))
