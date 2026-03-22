from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, ListView, DetailView
from django.urls import reverse_lazy
from .forms import CustomUserCreationForm
from .models import CustomUser, Message
from django.db.models import Q


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


from django.db.models import Q, OuterRef, Subquery, Count

class UserListView(LoginRequiredMixin, ListView):
    model = CustomUser
    template_name = "user_list.html"
    context_object_name = "users"

    def get_queryset(self):
        last_message = Message.objects.filter(
            (Q(sender=OuterRef('pk'), receiver=self.request.user)) |
            (Q(sender=self.request.user, receiver=OuterRef('pk')))
        ).order_by('-timestamp')

        unread_count = Message.objects.filter(
            sender=OuterRef('pk'),
            receiver=self.request.user,
            is_read=False
        ).values('sender').annotate(c=Count('*')).values('c')

        return CustomUser.objects.exclude(id=self.request.user.id).exclude(is_superuser=True).annotate(
            last_msg=Subquery(last_message.values('content')[:1]),
            last_msg_time=Subquery(last_message.values('timestamp')[:1]),
            unread_count=Subquery(unread_count)
        ).order_by('-last_msg_time')


@login_required
def chat_detail(request, username):
    other_user = CustomUser.objects.get(username=username)
    messages = Message.objects.filter(
        (Q(sender=request.user) & Q(receiver=other_user))
        | (Q(sender=other_user) & Q(receiver=request.user))
    ).order_by("timestamp")

    # Mark messages as read when entering chat
    Message.objects.filter(
        sender=other_user, receiver=request.user, is_read=False
    ).update(is_read=True)

    return render(
        request, "chat.html", {"other_user": other_user, "chat_messages": messages}
    )
