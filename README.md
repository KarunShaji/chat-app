# Real-Time Individual Chat Application

A real-time individual chat application built with Django (MVT) and Django Channels (WebSockets).

## Features

- Custom User Model (Email as primary identifier)
- User Registration, Login, and Logout
- Real-time Private Messaging using WebSockets
- Online Status Tracking (Green dot for online users)
- Message History and Read Status (✓ for sent, ✓✓ for read)
- Auto-scroll to the latest message in the chat interface

## Prerequisites

- Python 3.8+
- Virtual environment (recommended)

## Installation & Setup

1. **Clone the repository** (if applicable) or navigate to the project directory.

2. **Create and activate a virtual environment**:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

4. **Apply migrations**:

   ```bash
   python manage.py makemigrations chat
   python manage.py migrate
   ```

5. **Run the development server**:
   ```bash
   python manage.py runserver
   ```
   _Note: Using Daphne for ASGI support (automatically handled by Django when Channels is installed)._

## How to Use

1. Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.
2. Register a new user (User A).
3. Open another browser or an incognito window and register another user (User B).
4. Login as User A and User B respectively.
5. In User A's user list, click on User B to start a chat.
6. Messages sent between them will appear in real-time.
7. Observe the online status (green dot) when both users are logged in.

## Project Structure

- `chat/`: Core application containing models, views, and consumers.
- `chat_app/`: Project configuration (settings, asgi, urls).
- `templates/`: HTML templates for UI.
- `requirements.txt`: Project dependencies.
