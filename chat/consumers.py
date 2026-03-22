import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Message
from django.utils import timezone

User = get_user_model()

class DashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        self.group_name = f'user_dashboard_{self.user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def dashboard_update(self, event):
        await self.send(text_data=json.dumps(event))

    async def dashboard_typing(self, event):
        await self.send(text_data=json.dumps(event))

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        self.other_username = self.scope["url_route"]["kwargs"]["username"]
        self.other_user = await self.get_user(self.other_username)

        ids = sorted([self.user.id, self.other_user.id])
        self.room_group_name = f"chat_{ids[0]}_{ids[1]}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.update_user_status(True)
        await self.accept()

        await self.channel_layer.group_send(
            self.room_group_name, {"type": "read_receipt", "reader": self.user.username}
        )

    async def disconnect(self, close_code):
        await self.update_user_status(False)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get("type", "chat_message")

        if message_type == "chat_message":
            message_content = data.get("message", "").strip()

            if message_content:
                # Save message to database
                message_obj = await self.save_message(self.user, self.other_user, message_content)

                payload = {
                    "type": "chat_message",
                    "message": message_content,
                    "sender": self.user.username,
                    "timestamp": message_obj.timestamp.isoformat(),
                    "is_read": message_obj.is_read,
                }
                await self.channel_layer.group_send(self.room_group_name, payload)

                # Notify recipient's dashboard
                dashboard_group = f'user_dashboard_{self.other_user.id}'
                await self.channel_layer.group_send(
                    dashboard_group,
                    {
                        "type": "dashboard_update",
                        "sender_username": self.user.username,
                        "message": message_content,
                        "timestamp": message_obj.timestamp.isoformat(),
                    }
                )

        elif message_type == "typing":
            # Chat room typing
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_typing",
                    "sender": self.user.username,
                    "is_typing": data.get("is_typing", False),
                },
            )
            # Dashboard typing for recipient
            dashboard_group = f'user_dashboard_{self.other_user.id}'
            await self.channel_layer.group_send(
                dashboard_group,
                {
                    "type": "dashboard_typing",
                    "sender_username": self.user.username,
                    "is_typing": data.get("is_typing", False),
                }
            )

    async def chat_message(self, event):
        if self.user.username != event["sender"]:
            await self.mark_as_read(event["sender"])
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "read_receipt", "reader": self.user.username},
            )
        await self.send(text_data=json.dumps(event))

    async def user_typing(self, event):
        if self.user.username != event["sender"]:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'sender': event['sender'],
                'is_typing': event['is_typing']
            }))

    async def read_receipt(self, event):
        if self.user.username != event["reader"]:
            await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_user(self, username):
        return User.objects.get(username=username)

    @database_sync_to_async
    def save_message(self, sender, receiver, content):
        return Message.objects.create(sender=sender, receiver=receiver, content=content)

    @database_sync_to_async
    def update_user_status(self, is_online):
        User.objects.filter(id=self.user.id).update(is_online=is_online, last_seen=timezone.now())

    @database_sync_to_async
    def mark_as_read(self, sender_username):
        sender = User.objects.get(username=sender_username)
        Message.objects.filter(sender=sender, receiver=self.user, is_read=False).update(is_read=True)
