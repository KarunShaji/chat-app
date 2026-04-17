# API Integration Guide

This project exposes:

- A REST API for auth, user search, conversations, messages, and read receipts
- WebSocket endpoints for live chat updates, typing indicators, read receipts, and presence
- Swagger / OpenAPI docs for testing and inspection

## Base URLs

Use your deployed domain in production.

Local development examples:

- HTTP API base: `http://127.0.0.1:8000/api/v1/`
- OpenAPI schema: `http://127.0.0.1:8000/api/schema/`
- Swagger UI: `http://127.0.0.1:8000/api/docs/swagger/`
- ReDoc: `http://127.0.0.1:8000/api/docs/redoc/`
- WebSocket base: `ws://127.0.0.1:8000/ws/`

Production pattern:

- HTTP API base: `https://<your-domain>/api/v1/`
- Swagger UI: `https://<your-domain>/api/docs/swagger/`
- WebSocket base: `wss://<your-domain>/ws/`

## Authentication

### REST API auth

The mobile REST API uses DRF token auth.

Header:

```http
Authorization: Token <your_token>
```

Get a token from:

- `POST /api/v1/auth/register/`
- `POST /api/v1/auth/login/`

### WebSocket auth

WebSockets now support both:

- Django session/cookie auth for the existing browser client
- DRF token auth for mobile clients

Supported token transport methods:

- Query param: `?token=<your_token>`
- Header: `Authorization: Token <your_token>`
- Header: `Authorization: Bearer <your_token>`

For browser-based web apps, query-param token auth is usually the simplest option because browsers do not reliably allow custom websocket auth headers. For native mobile apps, either query param or `Authorization` header is fine.

If token auth fails, the websocket connection will be rejected during connect.

## REST Endpoints

### Authentication

`POST /api/v1/auth/register/`

Request:

```json
{
  "email": "alice@example.com",
  "username": "alice",
  "first_name": "Alice",
  "last_name": "Stone",
  "password": "strong-pass-123",
  "password_confirm": "strong-pass-123"
}
```

Response:

```json
{
  "token": "your_token_here",
  "user": {
    "id": 1,
    "username": "alice",
    "email": "alice@example.com",
    "first_name": "Alice",
    "last_name": "Stone",
    "full_name": "Alice Stone",
    "initial": "A",
    "is_online": false,
    "last_seen": "2026-04-17T12:00:00Z"
  }
}
```

`POST /api/v1/auth/login/`

Request:

```json
{
  "email": "alice@example.com",
  "password": "strong-pass-123"
}
```

`POST /api/v1/auth/logout/`

Requires token auth. Deletes the current user's token.

`GET /api/v1/auth/me/`

Returns the authenticated user profile.

### Users

`GET /api/v1/users/search/?q=<query>`

Search users by username, first name, last name, or email.

Example:

```http
GET /api/v1/users/search/?q=bob
```

Response:

```json
[
  {
    "id": 2,
    "username": "bob",
    "first_name": "Bob",
    "last_name": "Ray",
    "full_name": "Bob Ray",
    "initial": "B",
    "is_online": true,
    "last_seen": "2026-04-17T12:05:00Z"
  }
]
```

### Conversations

`GET /api/v1/conversations/`

Returns recent chats for the authenticated user.

Response shape:

```json
[
  {
    "id": 2,
    "username": "bob",
    "full_name": "Bob Ray",
    "initial": "B",
    "is_online": true,
    "last_seen": "2026-04-17T12:05:00Z",
    "last_message": "Hey there",
    "last_message_timestamp": "2026-04-17T12:04:00Z",
    "unread_count": 1
  }
]
```

### Messages

`GET /api/v1/conversations/<username>/messages/`

Returns the full conversation with the given user and marks unread incoming messages as read.

Example:

```http
GET /api/v1/conversations/bob/messages/
```

Response:

```json
{
  "other_user": {
    "id": 2,
    "username": "bob",
    "first_name": "Bob",
    "last_name": "Ray",
    "full_name": "Bob Ray",
    "initial": "B",
    "is_online": true,
    "last_seen": "2026-04-17T12:05:00Z"
  },
  "messages": [
    {
      "id": "a4e1df1c-2e1d-4ea6-b2af-111111111111",
      "client_id": "mobile-123",
      "sender": "alice",
      "receiver": "bob",
      "content": "Hello",
      "timestamp": "2026-04-17T12:01:00Z",
      "is_delivered": true,
      "is_read": true
    }
  ]
}
```

`POST /api/v1/conversations/<username>/messages/`

Creates a new message.

Request:

```json
{
  "content": "Hello from mobile",
  "client_id": "mobile-123"
}
```

Notes:

- `client_id` is optional
- If you provide `client_id`, the backend de-duplicates repeated sends from the same sender
- A retry with the same `client_id` and same message content returns the existing message instead of creating a duplicate
- Reusing the same `client_id` for different message content or a different conversation returns `409 Conflict`

Response:

```json
{
  "id": "a4e1df1c-2e1d-4ea6-b2af-111111111111",
  "client_id": "mobile-123",
  "sender": "alice",
  "receiver": "bob",
  "content": "Hello from mobile",
  "timestamp": "2026-04-17T12:06:00Z",
  "is_delivered": false,
  "is_read": false
}
```

`POST /api/v1/conversations/<username>/read/`

Marks unread incoming messages in that conversation as read.

Response:

```json
{
  "message_ids": [
    "a4e1df1c-2e1d-4ea6-b2af-111111111111"
  ],
  "marked_count": 1
}
```

## WebSocket Endpoints

### 1. Conversation socket

Use this when the user opens a specific chat.

URL pattern:

```text
ws://127.0.0.1:8000/ws/chat/<username>/
```

Production:

```text
wss://<your-domain>/ws/chat/<username>/
```

Example:

```text
ws://127.0.0.1:8000/ws/chat/bob/
```

Token-authenticated example:

```text
ws://127.0.0.1:8000/ws/chat/bob/?token=your_token_here
```

What it does:

- Receives live messages for that conversation
- Receives typing updates
- Receives read receipts
- Receives presence updates for the other user

### 2. Dashboard socket

Use this when the user is on the conversation list / inbox screen.

URL pattern:

```text
ws://127.0.0.1:8000/ws/dashboard/
```

Production:

```text
wss://<your-domain>/ws/dashboard/
```

Token-authenticated example:

```text
ws://127.0.0.1:8000/ws/dashboard/?token=your_token_here
```

What it does:

- Receives conversation preview updates
- Receives typing state for chat list rows
- Receives user online/offline status updates

## WebSocket Messages

All websocket message formats below apply after the socket has been authenticated with either a Django session or a DRF token.

Note:

- The server may send an initial `user_status_update` immediately after a successful connect
- A `ping` may not be the very first event you receive if that initial status event arrives first

### Send: chat message

```json
{
  "type": "chat_message",
  "client_id": "mobile-123",
  "message": "Hello"
}
```

### Receive: chat message

```json
{
  "type": "chat_message",
  "id": "a4e1df1c-2e1d-4ea6-b2af-111111111111",
  "client_id": "mobile-123",
  "message": "Hello",
  "sender": "alice",
  "timestamp": "2026-04-17T12:06:00Z",
  "is_delivered": false,
  "is_read": false
}
```

### Send: typing state

```json
{
  "type": "typing",
  "is_typing": true
}
```

### Receive: typing state

```json
{
  "type": "typing",
  "sender": "alice",
  "is_typing": true
}
```

### Receive: read receipt

```json
{
  "type": "read_receipt",
  "reader": "bob",
  "message_ids": [
    "a4e1df1c-2e1d-4ea6-b2af-111111111111"
  ]
}
```

### Receive: user status update

```json
{
  "type": "user_status_update",
  "username": "bob",
  "is_online": true,
  "last_seen": "2026-04-17T12:05:00Z"
}
```

### Receive on dashboard socket: conversation preview update

```json
{
  "type": "dashboard_update",
  "sender_username": "bob",
  "sender_initial": "B",
  "message": "Hey there",
  "timestamp": "2026-04-17T12:06:00Z",
  "is_delivered": false,
  "is_read": false
}
```

### Receive on dashboard socket: dashboard typing

```json
{
  "type": "dashboard_typing",
  "sender_username": "bob",
  "is_typing": true
}
```

### Ping / pong

The web client sends heartbeat pings periodically. You can do the same from mobile.

Send:

```json
{
  "type": "ping"
}
```

Receive:

```json
{
  "type": "pong"
}
```

## Recommended Mobile Integration Flow

### Login flow

1. Call `POST /api/v1/auth/login/`
2. Store the returned token securely
3. Send `Authorization: Token <token>` on all REST requests

### Chat list screen

1. Call `GET /api/v1/conversations/`
2. Open `/ws/dashboard/?token=<token>`
3. Update inbox rows from `dashboard_update`, `dashboard_typing`, and `user_status_update`

### Open chat screen

1. Call `GET /api/v1/conversations/<username>/messages/`
2. Open `/ws/chat/<username>/?token=<token>`
3. Send live messages through the socket or fallback to `POST /api/v1/conversations/<username>/messages/`
4. Mark unread messages read with:
   `POST /api/v1/conversations/<username>/read/`

### Example mobile websocket flow

Dashboard socket:

```text
ws://127.0.0.1:8000/ws/dashboard/?token=your_token_here
```

Conversation socket:

```text
ws://127.0.0.1:8000/ws/chat/bob/?token=your_token_here
```

Send typing:

```json
{
  "type": "typing",
  "is_typing": true
}
```

Send message:

```json
{
  "type": "chat_message",
  "client_id": "mobile-123",
  "message": "Hello from mobile socket"
}
```

If you retry a socket send with the same `client_id` and the original message already exists, the server will return the existing `chat_message` payload to the sending socket without re-broadcasting a duplicate event to everyone else.

## Swagger Testing

Open:

- `/api/docs/swagger/`

Then:

1. Run login or register
2. Copy the returned token
3. Click `Authorize`
4. Enter:

```text
Token <your_token>
```

5. Test protected endpoints directly from Swagger

## Notes

- REST and WebSocket auth can now use the same DRF token for mobile clients
- Web browsers can continue using the existing session-authenticated websocket flow
- `client_id` is still recommended for socket messages so reconnect/retry sends can be de-duplicated safely
