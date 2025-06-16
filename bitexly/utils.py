from channels.layers import get_channel_layer
from users.models import Notification
from django.core.mail import send_mail
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

def send_notification(user, title, message):
    # Save the notification in the database
    notification = Notification.objects.create(user=user, title=title, message=message)

    # Send the notification to the WebSocket group of the user
    channel_layer = get_channel_layer()
    channel_layer.group_send(
        f'user_{user.id}',  # Group name is user-specific
        {
            'type': 'send_notification',
            'content': {
                'title': title,
                'message': message,
                'created_at': notification.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        }
    )


def send_email(user, subject, message, code=None, action_url=None, action_text=None):
    html_content = render_to_string('base_template.html', {
        'user': user,
        'subject': subject,
        'message': message,
        'code': code,  # OTP or verification code
        'action_url': action_url,  # For buttons
        'action_text': action_text,
    })

    email = EmailMultiAlternatives(
        subject=subject,
        body=message,  # fallback text version
        from_email='Foodhybrid <no-reply@yourdomain.com>',
        to=[user.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

# def send_reset_otp_email(user, otp_code):
#     subject = "Verify Your Email"
#     message = f"Your OTP code is: {otp_code}"
#     send_mail(subject, message, None, [user.email])


