from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext

from .forms import EmailAuthenticationForm, ProfileForm, RegisterForm
from .guest import convert_guest, merge_guest_into
from .services import register_user


def _safe_next(request, default="dashboard:home", target=None):
    if target is None:
        target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
        return target
    return reverse(default)


def register(request):
    guest = request.user if request.user.is_authenticated and request.user.is_guest else None
    if request.user.is_authenticated and not guest:
        return redirect("dashboard:home")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        if guest:
            # keep the free mock the visitor already took
            user = convert_guest(guest, email=d["email"], password=d["password1"], first_name=d["first_name"],
                                 last_name=d["last_name"])
            update_session_auth_hash(request, user)
        else:
            user = register_user(
                email=d["email"], password=d["password1"], first_name=d["first_name"], last_name=d["last_name"],
            )
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, gettext("Welcome, %(name)s! All mocks are now open.") % {"name": user.first_name})
        return redirect(_safe_next(request))
    return render(request, "accounts/register.html", {"form": form, "guest": guest,
                                                      "next": request.GET.get("next", "")})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm

    def dispatch(self, request, *args, **kwargs):
        # A guest may log in (their free result moves to the account); real users go straight on.
        if request.user.is_authenticated and not request.user.is_guest:
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        guest = self.request.user if self.request.user.is_authenticated and self.request.user.is_guest else None
        response = super().form_valid(form)
        if merge_guest_into(guest, form.get_user()):
            messages.success(self.request, gettext("Your free mock result was added to your account."))
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["guest"] = self.request.user.is_authenticated and self.request.user.is_guest
        return ctx


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("core:home")


@login_required
def profile(request):
    if request.user.is_guest:
        return redirect("accounts:register")
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, gettext("Profile updated."))
        return redirect("accounts:profile")
    overview = None
    if request.user.is_student:
        from dashboard.insights import results_overview
        overview = results_overview(request.user)
    return render(request, "accounts/profile.html", {"form": form, "overview": overview})


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_guest:
            return redirect("accounts:register")
        return super().dispatch(request, *args, **kwargs)
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        messages.success(self.request, gettext("Your password was changed."))
        return super().form_valid(form)


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/emails/password_reset_email.txt"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
