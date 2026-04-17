from django.contrib.auth import authenticate, get_user_model
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.models import Message
from chat.services import ChatEventService, MessageIdempotencyConflict, MessageService

from .serializers import (
    AuthResponseSerializer,
    ConversationDetailSerializer,
    ConversationSummarySerializer,
    CurrentUserSerializer,
    LoginSerializer,
    MessageSerializer,
    PublicUserSerializer,
    ReadConversationResponseSerializer,
    RegisterSerializer,
    SendMessageSerializer,
)

User = get_user_model()


def get_conversation_queryset(user, other_user):
    return Message.objects.filter(
        (Q(sender=user) & Q(receiver=other_user))
        | (Q(sender=other_user) & Q(receiver=user))
    ).order_by("timestamp")


def get_chat_partner_or_404(request_user, username):
    return get_object_or_404(
        User.objects.exclude(id=request_user.id).exclude(is_superuser=True),
        username=username,
    )


def get_recent_chat_queryset(user, query=""):
    last_message = Message.objects.filter(
        (Q(sender=OuterRef("pk"), receiver=user))
        | (Q(sender=user, receiver=OuterRef("pk")))
    ).order_by("-timestamp")

    unread_count = (
        Message.objects.filter(sender=OuterRef("pk"), receiver=user, is_read=False)
        .values("sender")
        .annotate(c=Count("*"))
        .values("c")
    )

    queryset = (
        User.objects.exclude(id=user.id)
        .exclude(is_superuser=True)
        .annotate(
            last_msg=Subquery(last_message.values("content")[:1]),
            last_msg_time=Subquery(last_message.values("timestamp")[:1]),
            unread_count=Subquery(unread_count),
        )
    )

    if query:
        return queryset.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        ).order_by("-last_msg_time", "username")

    return (
        queryset.filter(
            Q(sent_messages__receiver=user) | Q(received_messages__sender=user)
        )
        .distinct()
        .order_by("-last_msg_time", "username")
    )


def mark_conversation_as_read(user, other_user):
    unread_ids = list(
        Message.objects.filter(
            sender=other_user,
            receiver=user,
            is_read=False,
        ).values_list("public_id", flat=True)
    )
    if unread_ids:
        Message.objects.filter(public_id__in=unread_ids).update(
            is_read=True,
            is_delivered=True,
        )
        ChatEventService.broadcast_read_receipt(
            reader_username=user.username,
            message_ids=[str(message_id) for message_id in unread_ids],
            user_a_id=user.id,
            user_b_id=other_user.id,
        )
    return unread_ids


class RegisterAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Authentication"],
        request=RegisterSerializer,
        responses={201: AuthResponseSerializer},
        examples=[
            OpenApiExample(
                "Register",
                value={
                    "email": "alice@example.com",
                    "username": "alice",
                    "first_name": "Alice",
                    "last_name": "Stone",
                    "password": "strong-pass-123",
                    "password_confirm": "strong-pass-123",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        payload = {"token": token.key, "user": user}
        return Response(
            AuthResponseSerializer(payload).data, status=status.HTTP_201_CREATED
        )


class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Authentication"],
        request=LoginSerializer,
        responses={
            200: AuthResponseSerializer,
            400: OpenApiResponse(description="Invalid credentials."),
        },
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user = authenticate(request=request, username=email, password=password)
        if user is None:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token, _ = Token.objects.get_or_create(user=user)
        payload = {"token": token.key, "user": user}
        return Response(AuthResponseSerializer(payload).data)


class LogoutAPIView(APIView):
    @extend_schema(
        tags=["Authentication"],
        request=None,
        responses={204: OpenApiResponse(description="Token deleted.")},
    )
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserAPIView(APIView):
    @extend_schema(tags=["Authentication"], responses={200: CurrentUserSerializer})
    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)


class UserSearchAPIView(APIView):
    @extend_schema(
        tags=["Users"],
        responses={200: PublicUserSerializer(many=True)},
    )
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response([])

        users = (
            User.objects.exclude(id=request.user.id)
            .exclude(is_superuser=True)
            .filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )[:10]
        )
        return Response(PublicUserSerializer(users, many=True).data)


class ConversationListAPIView(APIView):
    @extend_schema(
        tags=["Conversations"],
        responses={200: ConversationSummarySerializer(many=True)},
    )
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        queryset = get_recent_chat_queryset(request.user, query=query)
        return Response(ConversationSummarySerializer(queryset, many=True).data)


class ConversationMessagesAPIView(APIView):
    @extend_schema(
        tags=["Messages"],
        responses={200: ConversationDetailSerializer},
    )
    def get(self, request, username):
        other_user = get_chat_partner_or_404(request.user, username)
        mark_conversation_as_read(request.user, other_user)
        messages = get_conversation_queryset(request.user, other_user)
        payload = {
            "other_user": other_user,
            "messages": messages,
        }
        return Response(ConversationDetailSerializer(payload).data)

    @extend_schema(
        tags=["Messages"],
        request=SendMessageSerializer,
        responses={
            200: MessageSerializer,
            201: MessageSerializer,
            409: OpenApiResponse(
                description="The provided client_id has already been used for a different message."
            ),
        },
    )
    def post(self, request, username):
        other_user = get_chat_partner_or_404(request.user, username)
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content = serializer.validated_data["content"]
        client_id = serializer.validated_data.get("client_id") or None

        try:
            message, created = MessageService.create_or_get_message(
                sender=request.user,
                receiver=other_user,
                content=content,
                client_id=client_id,
            )
        except MessageIdempotencyConflict as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        if created:
            ChatEventService.broadcast_message(message)
            response_status = status.HTTP_201_CREATED
        else:
            response_status = status.HTTP_200_OK
        return Response(MessageSerializer(message).data, status=response_status)


class MarkConversationReadAPIView(APIView):
    @extend_schema(
        tags=["Messages"],
        request=None,
        responses={200: ReadConversationResponseSerializer},
    )
    def post(self, request, username):
        other_user = get_chat_partner_or_404(request.user, username)
        message_ids = mark_conversation_as_read(request.user, other_user)
        return Response(
            {
                "message_ids": message_ids,
                "marked_count": len(message_ids),
            }
        )
