from django.db import connection, transaction
from django.db.models import Max


def assign_next_integer_pk(instance):
    """
    Compatibility helper for the approved SIAB physical schema.

    The inspectdb models use IntegerField primary keys and the current database
    has no default or sequence for those columns. This function must run inside
    the same transaction that saves the object: it locks the target table and
    assigns MAX(pk) + 1 without altering PostgreSQL structures.
    """
    pk_field = instance._meta.pk
    pk_attname = pk_field.attname

    if getattr(instance, pk_attname):
        return instance

    table_name = connection.ops.quote_name(instance._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(f"LOCK TABLE {table_name} IN EXCLUSIVE MODE")

    next_id = (
        instance.__class__._default_manager.aggregate(max_id=Max(pk_attname))[
            "max_id"
        ]
        or 0
    ) + 1
    setattr(instance, pk_attname, next_id)
    return instance


def save_new_model_form(form, before_save=None):
    with transaction.atomic():
        instance = form.save(commit=False)
        if before_save:
            before_save(instance)
        assign_next_integer_pk(instance)
        instance.save()
        form.save_m2m()
    return instance
