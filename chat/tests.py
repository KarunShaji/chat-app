from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Message

User = get_user_model()


class ChatViewTests(TestCase):
    def setUp(self):
        self.password = "strong-pass-123"
        self.alice = User.objects.create_user(
            email="alice@example.com",
            username="alice",
            password=self.password,
        )
        self.bob = User.objects.create_user(
            email="bob@example.com",
            username="bob",
            password=self.password,
        )
        self.client = Client()
        self.client.login(username=self.alice.email, password=self.password)

    def test_chat_messages_api_marks_messages_read(self):
        message = Message.objects.create(
            sender=self.bob,
            receiver=self.alice,
            content="hello",
        )

        response = self.client.get(
            reverse("chat_messages_api", args=[self.bob.username])
        )

        self.assertEqual(response.status_code, 200)
        message.refresh_from_db()
        self.assertTrue(message.is_read)
        self.assertTrue(message.is_delivered)
        payload = response.json()
        self.assertEqual(payload["messages"][0]["content"], "hello")
        self.assertEqual(payload["messages"][0]["id"], str(message.public_id))

    def test_chat_detail_marks_messages_read_and_delivered(self):
        message = Message.objects.create(
            sender=self.bob,
            receiver=self.alice,
            content="hello again",
        )

        response = self.client.get(reverse("chat_detail", args=[self.bob.username]))

        self.assertEqual(response.status_code, 200)
        message.refresh_from_db()
        self.assertTrue(message.is_read)
        self.assertTrue(message.is_delivered)

    def test_user_search_api_excludes_current_user(self):
        response = self.client.get(reverse("user_search_api"), {"q": "ali"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["users"], [])

    def test_user_search_api_returns_matching_users(self):
        response = self.client.get(reverse("user_search_api"), {"q": "bo"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["users"][0]["username"], self.bob.username)

    def test_new_user_list_has_no_chat_rows_without_history(self):
        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 200)
        users = list(response.context["users"])
        self.assertEqual(users, [])


class MessageModelTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email="alice2@example.com",
            username="alice2",
            password="strong-pass-123",
        )
        self.bob = User.objects.create_user(
            email="bob2@example.com",
            username="bob2",
            password="strong-pass-123",
        )

    def test_message_public_id_is_generated(self):
        message = Message.objects.create(
            sender=self.alice,
            receiver=self.bob,
            content="hello",
        )

        self.assertIsNotNone(message.public_id)

    def test_sender_client_id_must_be_unique(self):
        Message.objects.create(
            sender=self.alice,
            receiver=self.bob,
            content="hello",
            client_id="abc123",
        )

        with self.assertRaises(IntegrityError):
            Message.objects.create(
                sender=self.alice,
                receiver=self.bob,
                content="duplicate",
                client_id="abc123",
            )


class ChatAPITests(APITestCase):
    def setUp(self):
        self.password = "strong-pass-123"
        self.alice = User.objects.create_user(
            email="alice-api@example.com",
            username="alice_api",
            password=self.password,
            first_name="Alice",
        )
        self.bob = User.objects.create_user(
            email="bob-api@example.com",
            username="bob_api",
            password=self.password,
            first_name="Bob",
        )
        self.token = Token.objects.create(user=self.alice)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_register_api_creates_user_and_returns_token(self):
        self.client.credentials()
        response = self.client.post(
            reverse("api_register"),
            {
                "email": "charlie@example.com",
                "username": "charlie",
                "first_name": "Charlie",
                "last_name": "Day",
                "password": self.password,
                "password_confirm": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["user"]["email"], "charlie@example.com")
        self.assertTrue(User.objects.filter(email="charlie@example.com").exists())

    def test_login_api_returns_token_for_email_credentials(self):
        self.client.credentials()
        response = self.client.post(
            reverse("api_login"),
            {"email": self.alice.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["username"], self.alice.username)
        self.assertEqual(response.data["token"], self.token.key)

    def test_me_api_returns_current_user(self):
        response = self.client.get(reverse("api_me"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], self.alice.email)
        self.assertEqual(response.data["username"], self.alice.username)

    def test_conversation_list_api_returns_recent_chats_with_unread_counts(self):
        Message.objects.create(
            sender=self.bob,
            receiver=self.alice,
            content="Need a reply",
        )

        response = self.client.get(reverse("api_conversations"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["username"], self.bob.username)
        self.assertEqual(response.data[0]["unread_count"], 1)
        self.assertEqual(response.data[0]["last_message"], "Need a reply")

    def test_conversation_messages_get_marks_messages_as_read(self):
        message = Message.objects.create(
            sender=self.bob,
            receiver=self.alice,
            content="hello from api test",
        )

        response = self.client.get(
            reverse("api_conversation_messages", args=[self.bob.username])
        )

        self.assertEqual(response.status_code, 200)
        message.refresh_from_db()
        self.assertTrue(message.is_read)
        self.assertTrue(message.is_delivered)
        self.assertEqual(response.data["messages"][0]["id"], str(message.public_id))

    def test_conversation_messages_post_creates_message(self):
        response = self.client.post(
            reverse("api_conversation_messages", args=[self.bob.username]),
            {"content": "sent from api", "client_id": "mobile-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["content"], "sent from api")
        self.assertEqual(response.data["sender"], self.alice.username)
        self.assertTrue(
            Message.objects.filter(
                sender=self.alice,
                receiver=self.bob,
                client_id="mobile-123",
            ).exists()
        )

    def test_conversation_messages_post_is_idempotent_for_same_client_id(self):
        first_response = self.client.post(
            reverse("api_conversation_messages", args=[self.bob.username]),
            {"content": "same message", "client_id": "mobile-repeat"},
            format="json",
        )
        second_response = self.client.post(
            reverse("api_conversation_messages", args=[self.bob.username]),
            {"content": "same message", "client_id": "mobile-repeat"},
            format="json",
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first_response.data["id"], second_response.data["id"])
        self.assertEqual(
            Message.objects.filter(
                sender=self.alice,
                receiver=self.bob,
                client_id="mobile-repeat",
            ).count(),
            1,
        )

    def test_conversation_messages_post_rejects_conflicting_client_id_reuse(self):
        self.client.post(
            reverse("api_conversation_messages", args=[self.bob.username]),
            {"content": "first message", "client_id": "mobile-conflict"},
            format="json",
        )

        response = self.client.post(
            reverse("api_conversation_messages", args=[self.bob.username]),
            {"content": "different message", "client_id": "mobile-conflict"},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("detail", response.data)

    def test_mark_conversation_read_endpoint_returns_marked_messages(self):
        first = Message.objects.create(
            sender=self.bob,
            receiver=self.alice,
            content="first",
        )
        second = Message.objects.create(
            sender=self.bob,
            receiver=self.alice,
            content="second",
        )

        response = self.client.post(
            reverse("api_conversation_read", args=[self.bob.username]),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["marked_count"], 2)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_read)
        self.assertTrue(second.is_read)


class TokenAuthenticatedWebSocketTests(TestCase):
    def setUp(self):
        self.password = "strong-pass-123"
        self.alice = User.objects.create_user(
            email="alice-ws@example.com",
            username="alice_ws",
            password=self.password,
        )
        self.bob = User.objects.create_user(
            email="bob-ws@example.com",
            username="bob_ws",
            password=self.password,
        )
        self.alice_token = Token.objects.create(user=self.alice)
        self.bob_token = Token.objects.create(user=self.bob)

    def test_dashboard_socket_accepts_token_query_param(self):
        async def scenario():
            from chat_app.asgi import application

            communicator = WebsocketCommunicator(
                application,
                f"/ws/dashboard/?token={self.alice_token.key}",
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_json_to({"type": "ping"})
            response_types = set()
            for _ in range(3):
                response = await communicator.receive_json_from()
                response_types.add(response["type"])
                if response["type"] == "pong":
                    break

            self.assertIn("pong", response_types)
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_chat_socket_typing_event_works_with_token_authenticated_users(self):
        async def scenario():
            from chat_app.asgi import application

            alice_socket = WebsocketCommunicator(
                application,
                f"/ws/chat/{self.bob.username}/?token={self.alice_token.key}",
            )
            bob_socket = WebsocketCommunicator(
                application,
                f"/ws/chat/{self.alice.username}/?token={self.bob_token.key}",
            )

            alice_connected, _ = await alice_socket.connect()
            bob_connected, _ = await bob_socket.connect()
            self.assertTrue(alice_connected)
            self.assertTrue(bob_connected)

            await alice_socket.send_json_to({"type": "typing", "is_typing": True})
            payload = await bob_socket.receive_json_from()
            self.assertEqual(
                payload,
                {
                    "type": "typing",
                    "sender": self.alice.username,
                    "is_typing": True,
                },
            )

            await alice_socket.disconnect()
            await bob_socket.disconnect()

        async_to_sync(scenario)()

    def test_dashboard_socket_accepts_token_authorization_header(self):
        async def scenario():
            from chat_app.asgi import application

            communicator = WebsocketCommunicator(
                application,
                "/ws/dashboard/",
                headers=[
                    (
                        b"authorization",
                        f"Token {self.alice_token.key}".encode("utf-8"),
                    )
                ],
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_dashboard_socket_rejects_invalid_token(self):
        async def scenario():
            from chat_app.asgi import application

            communicator = WebsocketCommunicator(
                application,
                "/ws/dashboard/?token=invalid-token",
            )
            connected, _ = await communicator.connect()
            self.assertFalse(connected)

        async_to_sync(scenario)()
