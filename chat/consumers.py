import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from .models import Message
from .services import MessageIdempotencyConflict, MessageService, PresenceService

User = get_user_model()


class PresenceConsumerMixin:
    status_group = "users_status"

    async def add_presence_groups(self, include_dashboard_group=True):
        self.group_name = f"user_dashboard_{self.user.id}"
        if include_dashboard_group:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add(self.status_group, self.channel_name)

    async def remove_presence_groups(self, include_dashboard_group=True):
        if include_dashboard_group and hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await self.channel_layer.group_discard(self.status_group, self.channel_name)

    async def handle_presence_change(self, is_online):
        count = await self.update_connection_count(is_online)
        should_update = (is_online and count == 1) or (not is_online and count == 0)
        if should_update:
            last_seen = await self.set_user_status_db(is_online)
            await self.broadcast_user_status(is_online, last_seen)

    @database_sync_to_async
    def update_connection_count(self, increment):
        if increment:
            return PresenceService.increment_connections(self.user.id)
        return PresenceService.decrement_connections(self.user.id)

    @database_sync_to_async
    def set_user_status_db(self, is_online):
        return PresenceService.set_status(self.user.id, is_online)

    @database_sync_to_async
    def broadcast_user_status(self, is_online, last_seen):
        PresenceService.broadcast_status(self.user.username, is_online, last_seen)

    async def send_error(self, detail, code="bad_request"):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "error",
                    "code": code,
                    "detail": detail,
                }
            )
        )

    def parse_boolean(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)


class DashboardConsumer(PresenceConsumerMixin, AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        await self.add_presence_groups(include_dashboard_group=True)
        await self.accept()
        await self.handle_presence_change(True)

    async def disconnect(self, close_code):
        await self.remove_presence_groups(include_dashboard_group=True)
        if self.user.is_authenticated:
            await self.handle_presence_change(False)

    async def dashboard_update(self, event):
        await self.send(text_data=json.dumps(event))

    async def dashboard_typing(self, event):
        await self.send(text_data=json.dumps(event))

    async def user_status_update(self, event):
        await self.send(text_data=json.dumps(event))

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON payload.", code="invalid_json")
            return

        if data.get("type") == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
        else:
            await self.send_error(
                "Unsupported dashboard event type.", code="unsupported_type"
            )


class ChatConsumer(PresenceConsumerMixin, AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        self.other_username = self.scope["url_route"]["kwargs"]["username"]
        try:
            self.other_user = await self.get_user(self.other_username)
        except ObjectDoesNotExist:
            await self.close(code=4404)
            return

        ids = sorted([self.user.id, self.other_user.id])
        self.room_group_name = f"chat_{ids[0]}_{ids[1]}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.add_presence_groups(include_dashboard_group=False)
        await self.accept()

        await self.handle_presence_change(True)
        read_message_ids = await self.mark_existing_messages_read()
        if read_message_ids:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "read_receipt",
                    "reader": self.user.username,
                    "message_ids": [str(message_id) for message_id in read_message_ids],
                },
            )

    async def disconnect(self, close_code):
        if self.user.is_authenticated:
            await self.handle_presence_change(False)
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )
        await self.remove_presence_groups(include_dashboard_group=False)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON payload.", code="invalid_json")
            return

        message_type = data.get("type", "chat_message")

        if message_type == "chat_message":
            raw_message = data.get("message", "")
            if not isinstance(raw_message, str):
                await self.send_error(
                    "Message must be a string.", code="invalid_message"
                )
                return

            message_content = raw_message.strip()
            client_id = data.get("client_id")

            if message_content:
                try:
                    message_obj, created = await self.save_message(
                        self.user, self.other_user, message_content, client_id
                    )
                except MessageIdempotencyConflict as exc:
                    await self.send_error(str(exc), code="client_id_conflict")
                    return

                payload = {
                    "type": "chat_message",
                    "id": str(message_obj.public_id),
                    "client_id": message_obj.client_id,
                    "message": message_obj.content,
                    "sender": self.user.username,
                    "timestamp": message_obj.timestamp.isoformat(),
                    "is_delivered": message_obj.is_delivered,
                    "is_read": message_obj.is_read,
                }

                if created:
                    await self.channel_layer.group_send(self.room_group_name, payload)

                    # Notify recipient's dashboard
                    dashboard_group = f"user_dashboard_{self.other_user.id}"
                    await self.channel_layer.group_send(
                        dashboard_group,
                        {
                            "type": "dashboard_update",
                            "sender_username": self.user.username,
                            "sender_initial": self.user.username[0].upper(),
                            "message": message_obj.content,
                            "timestamp": message_obj.timestamp.isoformat(),
                            "is_delivered": message_obj.is_delivered,
                            "is_read": message_obj.is_read,
                        },
                    )
                else:
                    await self.send(text_data=json.dumps(payload))
            else:
                await self.send_error(
                    "Message content cannot be empty.",
                    code="empty_message",
                )

        elif message_type == "typing":
            is_typing = self.parse_boolean(data.get("is_typing", False))
            # Chat room typing
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_typing",
                    "sender": self.user.username,
                    "is_typing": is_typing,
                },
            )
            # Dashboard typing for recipient
            dashboard_group = f"user_dashboard_{self.other_user.id}"
            await self.channel_layer.group_send(
                dashboard_group,
                {
                    "type": "dashboard_typing",
                    "sender_username": self.user.username,
                    "is_typing": is_typing,
                },
            )
        elif message_type == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
        else:
            await self.send_error(
                "Unsupported chat event type.", code="unsupported_type"
            )

    async def chat_message(self, event):
        if self.user.username != event["sender"]:
            receipt = await self.mark_message_read(event["id"])
            await self.channel_layer.group_send(self.room_group_name, receipt)
        await self.send(text_data=json.dumps(event))

    async def user_typing(self, event):
        if self.user.username != event["sender"]:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "typing",
                        "sender": event["sender"],
                        "is_typing": event["is_typing"],
                    }
                )
            )

    async def read_receipt(self, event):
        if self.user.username != event["reader"]:
            await self.send(text_data=json.dumps(event))

    async def user_status_update(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_user(self, username):
        return (
            User.objects.exclude(id=self.user.id)
            .exclude(is_superuser=True)
            .get(username=username)
        )

    @database_sync_to_async
    def save_message(self, sender, receiver, content, client_id):
        return MessageService.create_or_get_message(
            sender=sender,
            receiver=receiver,
            content=content,
            client_id=client_id,
        )

    @database_sync_to_async
    def mark_message_read(self, public_id):
        try:
            message = Message.objects.get(public_id=public_id)
        except Message.DoesNotExist:
            return {
                "type": "read_receipt",
                "reader": self.user.username,
                "message_ids": [],
            }
        if message.receiver_id != self.user.id:
            return {
                "type": "read_receipt",
                "reader": self.user.username,
                "message_ids": [],
            }

        updated = False
        if not message.is_delivered or not message.is_read:
            message.is_delivered = True
            message.is_read = True
            message.save(update_fields=["is_delivered", "is_read"])
            updated = True

        return {
            "type": "read_receipt",
            "reader": self.user.username,
            "message_ids": [str(message.public_id)] if updated else [],
        }

    @database_sync_to_async
    def mark_existing_messages_read(self):
        unread_messages = list(
            Message.objects.filter(
                sender=self.other_user,
                receiver=self.user,
                is_read=False,
            ).values_list("public_id", flat=True)
        )
        if unread_messages:
            Message.objects.filter(public_id__in=unread_messages).update(
                is_read=True,
                is_delivered=True,
            )
        return unread_messages
