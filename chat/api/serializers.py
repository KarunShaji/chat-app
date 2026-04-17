from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from chat.models import Message

User = get_user_model()


class PublicUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    initial = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "initial",
            "is_online",
            "last_seen",
        ]
        read_only_fields = fields

    @extend_schema_field(str)
    def get_full_name(self, obj) -> str:
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return full_name or obj.username

    @extend_schema_field(str)
    def get_initial(self, obj) -> str:
        source = obj.first_name or obj.username or ""
        return source[:1].upper()


class CurrentUserSerializer(PublicUserSerializer):
    email = serializers.EmailField(read_only=True)

    class Meta(PublicUserSerializer.Meta):
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "initial",
            "is_online",
            "last_seen",
        ]
        read_only_fields = fields


class AuthResponseSerializer(serializers.Serializer):
    token = serializers.CharField(read_only=True)
    user = CurrentUserSerializer(read_only=True)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "email",
            "username",
            "first_name",
            "last_name",
            "password",
            "password_confirm",
        ]

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_username(self, value):
        username = value.strip()
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError(
                "A user with this username already exists."
            )
        return username

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Password confirmation does not match."}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return value.strip().lower()


class ConversationSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    initial = serializers.SerializerMethodField()
    last_message = serializers.CharField(source="last_msg", read_only=True)
    last_message_timestamp = serializers.DateTimeField(
        source="last_msg_time", read_only=True
    )
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "initial",
            "is_online",
            "last_seen",
            "last_message",
            "last_message_timestamp",
            "unread_count",
        ]
        read_only_fields = fields

    @extend_schema_field(str)
    def get_full_name(self, obj) -> str:
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return full_name or obj.username

    @extend_schema_field(str)
    def get_initial(self, obj) -> str:
        source = obj.first_name or obj.username or ""
        return source[:1].upper()

    @extend_schema_field(int)
    def get_unread_count(self, obj) -> int:
        return obj.unread_count or 0


class MessageSerializer(serializers.ModelSerializer):
    sender = serializers.CharField(source="sender.username", read_only=True)
    receiver = serializers.CharField(source="receiver.username", read_only=True)
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "client_id",
            "sender",
            "receiver",
            "content",
            "timestamp",
            "is_delivered",
            "is_read",
        ]
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False, trim_whitespace=True)
    client_id = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate_content(self, value):
        content = value.strip()
        if not content:
            raise serializers.ValidationError("Message content cannot be empty.")
        return content


class ConversationDetailSerializer(serializers.Serializer):
    other_user = PublicUserSerializer(read_only=True)
    messages = MessageSerializer(many=True, read_only=True)


class ReadConversationResponseSerializer(serializers.Serializer):
    message_ids = serializers.ListField(child=serializers.UUIDField(), read_only=True)
    marked_count = serializers.IntegerField(read_only=True)
