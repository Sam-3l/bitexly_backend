"""
WSGI config for foodhybrid project.

It exposes the WSGI callable as a module-level variable named ``application``.
test
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bitexly.settings')

application = get_wsgi_application()
