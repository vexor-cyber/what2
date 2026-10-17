from django.conf import settings
from django.shortcuts import redirect

from .models import Subscription


class SubscriptionRequiredMiddleware:
    public_paths = {"/", "/workbooks/", "/settings/", "/subscription/", "/register/", "/login/", "/logout/"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if not user.is_authenticated or user.is_staff:
            return None
        static_prefix = "/" + settings.STATIC_URL.lstrip("/")
        if request.path_info in self.public_paths or request.path_info.startswith(static_prefix):
            return None
        try:
            has_access = user.subscription.is_active
        except Subscription.DoesNotExist:
            has_access = False
        if not has_access:
            return redirect("subscription")
        return None