import logging

from django.core.paginator import Paginator
from django.db import DatabaseError


logger = logging.getLogger(__name__)


def paginate(request, queryset, per_page=15):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def safe_count(model):
    try:
        return model.objects.count()
    except DatabaseError:
        logger.exception("Could not count %s", model.__name__)
        return None
