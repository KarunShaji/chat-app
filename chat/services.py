from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from .models import Message

User = get_user_model()


class PresenceService:
    @staticmethod
    def connection_cache_key(user_id):
        return f"user_conn_count_{user_id}"

    @classmethod
    def increment_connections(cls, user_id):
        cache_key = cls.connection_cache_key(user_id)
        count = cache.get(cache_key, 0) + 1
        cache.set(cache_key, count, timeout=None)
        return count

    @classmethod
    def decrement_connections(cls, user_id):
        cache_key = cls.connection_cache_key(user_id)
        count = max(0, cache.get(cache_key, 0) - 1)
        cache.set(cache_key, count, timeout=None)
        return count

    @classmethod
    def set_status(cls, user_id, is_online):
        now = timezone.now()
        User.objects.filter(id=user_id).update(is_online=is_online, last_seen=now)
        return now

    @classmethod
    def broadcast_status(cls, username, is_online, last_seen=None):
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        async_to_sync(channel_layer.group_send)(
            "users_status",
            {
                "type": "user_status_update",
                "username": username,
                "is_online": is_online,
                "last_seen": (last_seen or timezone.now()).isoformat(),
            },
        )


class ChatEventService:
    @staticmethod
    def chat_group_name(user_a_id, user_b_id):
        ids = sorted([user_a_id, user_b_id])
        return f"chat_{ids[0]}_{ids[1]}"

    @staticmethod
    def dashboard_group_name(user_id):
        return f"user_dashboard_{user_id}"

    @staticmethod
    def send_group_event(group_name, payload):
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(group_name, payload)

    @classmethod
    def broadcast_message(cls, message):
        cls.send_group_event(
            cls.chat_group_name(message.sender_id, message.receiver_id),
            {
                "type": "chat_message",
                "id": str(message.public_id),
                "client_id": message.client_id,
                "message": message.content,
                "sender": message.sender.username,
                "timestamp": message.timestamp.isoformat(),
                "is_delivered": message.is_delivered,
                "is_read": message.is_read,
            },
        )
        cls.send_group_event(
            cls.dashboard_group_name(message.receiver_id),
            {
                "type": "dashboard_update",
                "sender_username": message.sender.username,
                "sender_initial": message.sender.username[:1].upper(),
                "message": message.content,
                "timestamp": message.timestamp.isoformat(),
                "is_delivered": message.is_delivered,
                "is_read": message.is_read,
            },
        )

    @classmethod
    def broadcast_read_receipt(cls, reader_username, message_ids, user_a_id, user_b_id):
        if not message_ids:
            return
        cls.send_group_event(
            cls.chat_group_name(user_a_id, user_b_id),
            {
                "type": "read_receipt",
                "reader": reader_username,
                "message_ids": message_ids,
            },
        )


class MessageIdempotencyConflict(Exception):
    pass


class MessageService:
    @staticmethod
    def create_or_get_message(sender, receiver, content, client_id=None):
        if not client_id:
            return (
                Message.objects.create(
                    sender=sender,
                    receiver=receiver,
                    content=content,
                ),
                True,
            )

        message, created = Message.objects.get_or_create(
            sender=sender,
            client_id=client_id,
            defaults={
                "receiver": receiver,
                "content": content,
            },
        )
        if not created and (
            message.receiver_id != receiver.id or (message.content or "") != content
        ):
            raise MessageIdempotencyConflict(
                "This client_id has already been used for a different message."
            )
        return message, created
