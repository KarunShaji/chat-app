from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path(
        "login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("", views.UserListView.as_view(), name="user_list"),
    path("chat/<str:username>/", views.chat_detail, name="chat_detail"),
    path(
        "api/messages/<str:username>/",
        views.chat_messages_api,
        name="chat_messages_api",
    ),
    path("api/users/search/", views.user_search_api, name="user_search_api"),
]
