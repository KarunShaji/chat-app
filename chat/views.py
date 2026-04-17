from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from .forms import CustomUserCreationForm
from .models import CustomUser, Message


class RegisterView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "register.html"
    success_url = reverse_lazy("user_list")

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        return redirect(self.success_url)

    def form_invalid(self, form):
        print("Form Errors:", form.errors)
        return super().form_invalid(form)


class UserListView(LoginRequiredMixin, ListView):
    model = CustomUser
    template_name = "user_list.html"
    context_object_name = "users"

    def get_queryset(self):
        query = self.request.GET.get("q")

        last_message = Message.objects.filter(
            (Q(sender=OuterRef("pk"), receiver=self.request.user))
            | (Q(sender=self.request.user, receiver=OuterRef("pk")))
        ).order_by("-timestamp")

        unread_count = (
            Message.objects.filter(
                sender=OuterRef("pk"), receiver=self.request.user, is_read=False
            )
            .values("sender")
            .annotate(c=Count("*"))
            .values("c")
        )

        queryset = (
            CustomUser.objects.exclude(id=self.request.user.id)
            .exclude(is_superuser=True)
            .annotate(
                last_msg=Subquery(last_message.values("content")[:1]),
                last_msg_time=Subquery(last_message.values("timestamp")[:1]),
                unread_count=Subquery(unread_count),
            )
        )

        if query:
            queryset = queryset.filter(username__icontains=query)
        else:
            # Only show users we have a message history with
            queryset = queryset.filter(
                Q(sent_messages__receiver=self.request.user)
                | Q(received_messages__sender=self.request.user)
            ).distinct()

        return queryset.order_by("-last_msg_time")


@login_required
def user_search_api(request):
    query = request.GET.get("q", "")
    if len(query) < 1:
        return JsonResponse({"users": []})

    users = (
        CustomUser.objects.exclude(id=request.user.id)
        .exclude(is_superuser=True)
        .filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )[:10]
    )

    user_list = []
    for u in users:
        user_list.append(
            {
                "username": u.username,
                "full_name": f"{u.first_name} {u.last_name}".strip() or u.username,
                "initial": (u.first_name[0] if u.first_name else u.username[0]).upper(),
                "is_online": u.is_online,
            }
        )

    return JsonResponse({"users": user_list})


@login_required
def chat_detail(request, username):
    other_user = get_object_or_404(CustomUser, username=username)
    messages = Message.objects.filter(
        (Q(sender=request.user) & Q(receiver=other_user))
        | (Q(sender=other_user) & Q(receiver=request.user))
    ).order_by("timestamp")

    # Mark messages as read when entering chat
    Message.objects.filter(
        sender=other_user, receiver=request.user, is_read=False
    ).update(is_read=True, is_delivered=True)

    return render(
        request, "chat.html", {"other_user": other_user, "chat_messages": messages}
    )


@login_required
def chat_messages_api(request, username):
    other_user = get_object_or_404(CustomUser, username=username)
    messages = Message.objects.filter(
        (Q(sender=request.user) & Q(receiver=other_user))
        | (Q(sender=other_user) & Q(receiver=request.user))
    ).order_by("timestamp")

    # Mark as read
    Message.objects.filter(
        sender=other_user, receiver=request.user, is_read=False
    ).update(is_read=True, is_delivered=True)

    msg_list = []
    for m in messages:
        msg_list.append(
            {
                "id": str(m.public_id),
                "client_id": m.client_id,
                "sender": m.sender.username,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
                "is_read": m.is_read,
                "is_delivered": m.is_delivered,
            }
        )

    return JsonResponse(
        {
            "messages": msg_list,
            "other_user": {
                "username": other_user.username,
                "is_online": other_user.is_online,
                "last_seen": (
                    other_user.last_seen.isoformat() if other_user.last_seen else None
                ),
                "initial": other_user.username[0].upper(),
            },
        }
    )
