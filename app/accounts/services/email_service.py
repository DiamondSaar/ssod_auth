from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def send_user_created_email(user, temporary_password):
    """
    Отправка письма новому пользователю.

    Важно:
    временный пароль отправляется только один раз.
    В базе он хранится только как хэш.
    """

    if not user.email:
        return False

    subject = render_to_string(
        "accounts/emails/user_created_subject.txt",
        {
            "user": user,
        },
    ).strip()

    message = render_to_string(
        "accounts/emails/user_created_body.txt",
        {
            "user": user,
            "temporary_password": temporary_password,
            "login_url": "https://auth.ssod.pro/account/login/",
        },
    )

    sent_count = send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )

    return sent_count == 1
