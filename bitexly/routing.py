# your_project_name/routing.py
from django.urls import path
from users.consumers import NotificationConsumer

# Define your WebSocket URL patterns
websocket_urlpatterns = [
    path('ws/notifications/', NotificationConsumer.as_asgi()),  # Ensure this matches the client-side WebSocket URL
]
