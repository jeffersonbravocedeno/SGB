from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        if user.is_staff or user.is_superuser:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied

    return _wrapped_view
