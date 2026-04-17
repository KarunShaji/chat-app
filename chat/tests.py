from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

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
