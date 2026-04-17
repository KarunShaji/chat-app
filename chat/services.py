from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

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
