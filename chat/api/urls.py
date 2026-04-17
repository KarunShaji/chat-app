from django.urls import path

from chat.api.views import (
    ConversationListAPIView,
    ConversationMessagesAPIView,
    CurrentUserAPIView,
    LoginAPIView,
    LogoutAPIView,
    MarkConversationReadAPIView,
    RegisterAPIView,
    UserSearchAPIView,
)

urlpatterns = [
    path("auth/register/", RegisterAPIView.as_view(), name="api_register"),
    path("auth/login/", LoginAPIView.as_view(), name="api_login"),
    path("auth/logout/", LogoutAPIView.as_view(), name="api_logout"),
    path("auth/me/", CurrentUserAPIView.as_view(), name="api_me"),
    path("users/search/", UserSearchAPIView.as_view(), name="api_user_search"),
    path("conversations/", ConversationListAPIView.as_view(), name="api_conversations"),
    path(
        "conversations/<str:username>/messages/",
        ConversationMessagesAPIView.as_view(),
        name="api_conversation_messages",
    ),
    path(
        "conversations/<str:username>/read/",
        MarkConversationReadAPIView.as_view(),
        name="api_conversation_read",
    ),
]
