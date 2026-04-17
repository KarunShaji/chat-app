import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.username


class Message(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    client_id = models.CharField(max_length=64, blank=True, null=True)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_messages",
    )
    content = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_delivered = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["timestamp", "id"]
        indexes = [
            models.Index(fields=["sender", "receiver", "timestamp"]),
            models.Index(fields=["receiver", "is_read", "timestamp"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sender", "client_id"],
                condition=Q(client_id__isnull=False),
                name="unique_sender_client_message",
            )
        ]

    def __str__(self):
        preview = (self.content or "")[:20]
        return f"{self.sender.username} to {self.receiver.username}: {preview}"
