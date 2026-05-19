from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AuthEvent,
    CustomUser,
    Organization,
    Position,
    Product,
    ProductPermission,
    ProductRole,
    SSODAccessKey,
    UserEmail,
    UserMessenger,
    UserPhone,
    UserProductAccess,
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """
    Админка пользователя Auth Center.

    Пока это временный рабочий интерфейс.
    Позже сделаем свой UI, но Django Admin оставляем как техническую панель.
    """

    list_display = (
        "username",
        "full_name_ru",
        "organization",
        "position",
        "access_class",
        "is_active",
        "is_staff",
        "last_login",
    )

    list_filter = (
        "is_active",
        "is_staff",
        "access_class",
        "organization",
        "position",
    )

    search_fields = (
        "username",
        "last_name",
        "first_name",
        "middle_name",
        "email",
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "ССОД",
            {
                "fields": (
                    "uuid",
                    "middle_name",
                    "organization",
                    "position",
                    "access_class",
                    "must_change_password",
                    "blocked_reason",
                )
            },
        ),
    )

    readonly_fields = ("uuid",)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Управление продуктами экосистемы.

    Здесь администратор добавляет FinSoft, DomineX, Biographia
    и задает ссылки на реальные сервисы.
    """

    list_display = (
        "name",
        "code",
        "product_url",
        "is_active",
        "sort_order",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "code",
        "short_description",
    )

    ordering = (
        "sort_order",
        "name",
    )


@admin.register(UserProductAccess)
class UserProductAccessAdmin(admin.ModelAdmin):
    """
    Управление доступами пользователей к продуктам.

    Важно:
    доступ определяется через поле status,
    а не через boolean-флаг.
    """

    list_display = (
        "user",
        "product",
        "organization",
        "status",
        "updated_at",
    )

    list_filter = (
        "product",
        "status",
        "organization",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "product__name",
        "product__code",
    )

admin.site.register(Organization)
admin.site.register(Position)
admin.site.register(ProductPermission)
admin.site.register(ProductRole)
admin.site.register(UserEmail)
admin.site.register(UserPhone)
admin.site.register(UserMessenger)
admin.site.register(SSODAccessKey)
admin.site.register(AuthEvent)
