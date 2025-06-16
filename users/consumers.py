import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']  # Get the user from the WebSocket connection scope
        if self.user.is_authenticated:
            self.group_name = f"user_{self.user.id}"  # Define group for each user
            await self.channel_layer.group_add(
                self.group_name,  # Add the user to a group
                self.channel_name  # WebSocket connection's unique channel name
            )
            await self.accept()  # Accept the WebSocket connection
        else:
            await self.close()  # Close connection if not authenticated

    async def disconnect(self, close_code):
        # Leave group when disconnected
        if self.user.is_authenticated:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        # Handle incoming WebSocket messages (optional for actions like marking notifications as read)
        data = json.loads(text_data)
        if data.get("action") == "mark_read":
            # Process mark read functionality (example)
            pass

    async def send_notification(self, event):
        # Send notification to WebSocket client
        content = event["content"]
        await self.send(text_data=json.dumps(content))
