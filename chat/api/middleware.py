from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token


@database_sync_to_async
def get_user_for_token(token_key):
    try:
        return Token.objects.select_related("user").get(key=token_key).user
    except Token.DoesNotExist:
        return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        user = scope.get("user")
        if user is None or not user.is_authenticated:
            token_key = self._extract_token(scope)
            if token_key:
                scope["user"] = await get_user_for_token(token_key)
            else:
                scope["user"] = AnonymousUser()
        return await super().__call__(scope, receive, send)

    def _extract_token(self, scope):
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        query_token = query_params.get("token", [None])[0]
        if query_token:
            return query_token

        for name, value in scope.get("headers", []):
            if name.lower() != b"authorization":
                continue
            header_value = value.decode("utf-8").strip()
            if header_value.lower().startswith("token "):
                return header_value[6:].strip()
            if header_value.lower().startswith("bearer "):
                return header_value[7:].strip()
        return None


def TokenAuthMiddlewareStack(inner):
    return AuthMiddlewareStack(TokenAuthMiddleware(inner))
