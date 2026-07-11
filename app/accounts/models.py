import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Базовая абстрактная модель.

    Нужна, чтобы не повторять в каждой таблице:
    - когда запись создана;
    - когда запись обновлена.

    abstract = True означает:
    отдельная таблица TimeStampedModel в БД НЕ создается.
    Эти поля просто добавятся в дочерние модели.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        abstract = True


class AccessClass(models.TextChoices):
    """
    Класс доступа ССОД / Dominex.

    S — системный максимальный уровень.
    A — суперадмин.
    G — базовый пользователь ЛК.
    """

    S = "S", "S — системный"
    A = "A", "A — суперадмин"
    B = "B", "B — высокий"
    C = "C", "C — расширенный"
    D = "D", "D — средний"
    E = "E", "E — ограниченный"
    F = "F", "F — минимальный служебный"
    G = "G", "G — базовый пользователь"


class Organization(TimeStampedModel):
    """
    Организация / юридическое лицо.

    Это справочник.
    Пользователь НЕ вводит организацию свободным текстом.
    Он выбирает ее из справочника.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="UUID",
    )

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Наименование",
    )

    inn = models.CharField(
        max_length=12,
        blank=True,
        verbose_name="ИНН",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
    )

    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Position(TimeStampedModel):
    """
    Должность пользователя.

    Пока это простой справочник.
    В будущем можно привязывать должности к конкретной организации.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="UUID",
    )

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Должность",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    class Meta:
        verbose_name = "Должность"
        verbose_name_plural = "Должности"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    """
    Основная модель пользователя Auth Center.

    Наследуемся от AbstractUser, чтобы сохранить стандартные механизмы Django:
    - username;
    - password hash;
    - groups;
    - permissions;
    - is_staff;
    - is_superuser;
    - last_login.

    Но добавляем свои поля:
    - UUID для API и связей с Dominex/FinSoft;
    - отчество;
    - организация;
    - должность;
    - класс доступа;
    - требование сменить пароль при первом входе.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="UUID",
    )

    middle_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Отчество",
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="Организация",
    )

    position = models.ForeignKey(
        Position,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="Должность",
    )

    access_class = models.CharField(
        max_length=1,
        choices=AccessClass.choices,
        default=AccessClass.G,
        verbose_name="Класс доступа",
    )

    must_change_password = models.BooleanField(
        default=True,
        verbose_name="Требуется смена пароля",
    )

    blocked_reason = models.TextField(
        blank=True,
        verbose_name="Причина блокировки",
    )
    birth_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата рождения",
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        null=True,
        blank=True,
        verbose_name="Аватар",
    )

    admin_comment = models.TextField(
        blank=True,
        verbose_name="Комментарий администратора",
        help_text="Виден только администраторам системы.",
    )

    public_comment = models.TextField(
        blank=True,
        verbose_name="Комментарий для пользователя",
        help_text="Виден самому пользователю.",
    )

    system_role = models.ForeignKey(
        "SystemRole",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="Роль в системе",
    )


    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["last_name", "first_name", "username"]

    @property
    def full_name_ru(self):
        """
        ФИО одной строкой.

        Используем для таблиц, карточек и API.
        """
        parts = [
            self.last_name,
            self.first_name,
            self.middle_name,
        ]
        return " ".join(part for part in parts if part).strip()

    def __str__(self):
        return self.full_name_ru or self.username


class Product(TimeStampedModel):
    """
    Продукт / сервис ССОД.

    Примеры:
    - dominex
    - finsoft
    - ssod_lk

    Именно по product.code другие системы будут проверять права.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="UUID",
    )

    code = models.SlugField(
        max_length=80,
        unique=True,
        verbose_name="Код продукта",
        help_text="Например: dominex, finsoft, ssod_lk",
    )

    name = models.CharField(
        max_length=255,
        verbose_name="Название",
    )

    short_description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Краткое описание",
    )

    second_line = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Дополнительная строка",
    )

    product_url = models.URLField(
        blank=True,
        verbose_name="Адрес продукта",
    )

    logo = models.ImageField(
        upload_to="product_logos/",
        blank=True,
        null=True,
        verbose_name="Логотип продукта",
    )

    sort_order = models.PositiveIntegerField(
        default=100,
        verbose_name="Порядок сортировки",
    )


    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    class Meta:
        verbose_name = "Продукт"
        verbose_name_plural = "Продукты"
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class ProductPermission(TimeStampedModel):
    """
    Конкретное право внутри продукта.

    Например:
    - inventory.devices.view
    - inventory.devices.edit
    - tickets.create

    Dominex потом будет спрашивать Auth Center:
    можно ли пользователю выполнить конкретное permission.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="UUID",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="permissions",
        verbose_name="Продукт",
    )

    code = models.CharField(
        max_length=150,
        verbose_name="Код права",
    )

    name = models.CharField(
        max_length=255,
        verbose_name="Название права",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )

    class Meta:
        verbose_name = "Право продукта"
        verbose_name_plural = "Права продуктов"
        ordering = ["product__code", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "code"],
                name="unique_permission_code_per_product",
            )
        ]

    def __str__(self):
        return f"{self.product.code}: {self.code}"


class ProductRole(TimeStampedModel):
    """
    Роль внутри продукта.

    Роль = набор прав.
    Например для Dominex:
    - inventory_viewer
    - inventory_admin
    - service_operator
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="UUID",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="roles",
        verbose_name="Продукт",
    )

    code = models.SlugField(
        max_length=100,
        verbose_name="Код роли",
    )

    name = models.CharField(
        max_length=255,
        verbose_name="Название роли",
    )

    permissions = models.ManyToManyField(
        ProductPermission,
        blank=True,
        related_name="roles",
        verbose_name="Права",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    class Meta:
        verbose_name = "Роль продукта"
        verbose_name_plural = "Роли продуктов"
        ordering = ["product__code", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "code"],
                name="unique_role_code_per_product",
            )
        ]

    def __str__(self):
        return f"{self.product.code}: {self.name}"


class UserProductAccess(TimeStampedModel):
    """
    Доступ пользователя к конкретному продукту.

    Это ключевая таблица для централизованного контроля.

    Например:
    Пользователь Иванов имеет доступ к Dominex
    от организации АС Компонент
    с ролью inventory_viewer
    с 01.05.2026 по 31.05.2026.

    Если status = suspended, Dominex должен отказать в доступе.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        SUSPENDED = "suspended", "Приостановлен"
        REVOKED = "revoked", "Отозван"

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="UUID",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_accesses",
        verbose_name="Пользователь",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="user_accesses",
        verbose_name="Продукт",
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="product_accesses",
        verbose_name="Организация",
    )

    role = models.ForeignKey(
        ProductRole,
        on_delete=models.PROTECT,
        related_name="user_accesses",
        verbose_name="Роль",
    )

    access_class = models.CharField(
        max_length=1,
        choices=AccessClass.choices,
        default=AccessClass.G,
        verbose_name="Класс доступа",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="Статус доступа",
    )

    valid_from = models.DateTimeField(
        default=timezone.now,
        verbose_name="Доступ действует с",
    )

    valid_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Доступ действует до",
    )

    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
    )

    dominex_grant_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="ID гранта в Dominex",
        help_text="ProductAccessGrant.id из Dominex Core - если задан, эта запись является проекцией/кэшем, а не локально управляемой.",
    )

    synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Синхронизировано из Dominex",
    )

    class Meta:
        verbose_name = "Доступ пользователя к продукту"
        verbose_name_plural = "Доступы пользователей к продуктам"
        ordering = ["user", "product", "organization"]

    def is_currently_active(self):
        """
        Проверка актуальности доступа.

        Именно такую логику потом будет использовать API:
        - пользователь активен;
        - доступ не приостановлен;
        - срок действия не истек.
        """
        now = timezone.now()

        if self.status != self.Status.ACTIVE:
            return False

        if self.valid_from and self.valid_from > now:
            return False

        if self.valid_to and self.valid_to < now:
            return False

        return True

    def __str__(self):
        return f"{self.user} → {self.product.code} / {self.role.code}"


class UserEmail(TimeStampedModel):
    """
    Почтовые адреса пользователя.

    Отдельная таблица нужна, потому что адресов может быть несколько:
    - рабочий;
    - личный;
    - дополнительный.
    """

    class EmailType(models.TextChoices):
        WORK = "work", "Рабочая"
        PERSONAL = "personal", "Личная"
        OTHER = "other", "Другая"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="emails",
        verbose_name="Пользователь",
    )

    email_type = models.CharField(
        max_length=20,
        choices=EmailType.choices,
        default=EmailType.WORK,
        verbose_name="Тип почты",
    )

    email = models.EmailField(
        verbose_name="Email",
    )

    is_primary = models.BooleanField(
        default=False,
        verbose_name="Основная",
    )
    comment = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Комментарий",
        help_text="Например: рабочая почта, для уведомлений",
    )



    class Meta:
        verbose_name = "Email пользователя"
        verbose_name_plural = "Email пользователей"
        ordering = ["user", "-is_primary", "email"]

    def __str__(self):
        return f"{self.user}: {self.email}"


class UserPhone(TimeStampedModel):
    """
    Телефоны пользователя.

    Храним код страны отдельно, чтобы потом удобно форматировать номера.
    """

    class PhoneType(models.TextChoices):
        WORK = "work", "Рабочий"
        MOBILE = "mobile", "Мобильный"
        OTHER = "other", "Другой"

    # Международный формат: от 5 до 15 цифр после кода страны.
    # Примеры: 9036709699, 555123456
    # Код страны хранится отдельно в поле country_code.
    phone_validator = RegexValidator(
        regex=r"^\d{5,15}$",
        message="Только цифры, от 5 до 15 символов.",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="phones",
        verbose_name="Пользователь",
    )

    phone_type = models.CharField(
        max_length=20,
        choices=PhoneType.choices,
        default=PhoneType.WORK,
        verbose_name="Тип телефона",
    )

    country_code = models.CharField(
        max_length=8,
        default="+7",
        verbose_name="Код страны",
    )

    number = models.CharField(
        max_length=15,
        validators=[phone_validator],
        verbose_name="Номер",
        help_text="Только цифры без пробелов и тире. Например: 9036709699",
    )
    comment = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Комментарий",
        help_text="Например: рабочий, звонить с 9 до 18",
    )

    is_primary = models.BooleanField(
        default=False,
        verbose_name="Основной",
    )

    class Meta:
        verbose_name = "Телефон пользователя"
        verbose_name_plural = "Телефоны пользователей"
        ordering = ["user", "-is_primary", "phone_type"]

    def __str__(self):
        return f"{self.user}: {self.country_code} {self.number}"


class UserMessenger(TimeStampedModel):
    """
    Мессенджеры пользователя.

    Каждая запись = тип мессенджера + идентификатор.
    Например:
    Telegram + @username
    Matrix + @user:ssod.pro
    Compass + internal_id
    """

    class MessengerType(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        MATRIX = "matrix", "Matrix"
        COMPASS = "compass", "Compass"
        OTHER = "other", "Другой"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="messengers",
        verbose_name="Пользователь",
    )

    messenger_type = models.CharField(
        max_length=30,
        choices=MessengerType.choices,
        default=MessengerType.TELEGRAM,
        verbose_name="Тип мессенджера",
    )

    identifier = models.CharField(
        max_length=255,
        verbose_name="Идентификатор",
    )

    is_primary = models.BooleanField(
        default=False,
        verbose_name="Основной",
    )

    class Meta:
        verbose_name = "Мессенджер пользователя"
        verbose_name_plural = "Мессенджеры пользователей"
        ordering = ["user", "-is_primary", "messenger_type"]

    def __str__(self):
        return f"{self.user}: {self.messenger_type} {self.identifier}"


class SSODAccessKey(TimeStampedModel):
    """
    Ключ доступа ССОД.

    Важно:
    здесь НЕ храним приватный ключ пользователя.
    Здесь храним только публичные/служебные данные:
    - fingerprint;
    - статус;
    - сроки;
    - кому принадлежит.

    Приватный ключ должен быть у пользователя или в защищенном хранилище,
    но не просто текстом в БД.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        REVOKED = "revoked", "Отозван"
        EXPIRED = "expired", "Истек"
        LOST = "lost", "Утерян"

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="UUID",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ssod_keys",
        verbose_name="Пользователь",
    )

    name = models.CharField(
        max_length=255,
        verbose_name="Название ключа",
        help_text="Например: Ноутбук Владимира, Рабочий ПК, Тестовый ключ",
    )

    fingerprint_sha256 = models.CharField(
        max_length=128,
        unique=True,
        verbose_name="SHA256 fingerprint",
    )

    public_key_pem = models.TextField(
        blank=True,
        verbose_name="Публичный ключ PEM",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="Статус",
    )

    issued_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Дата выпуска",
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Истекает",
    )

    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата отзыва",
    )

    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Последнее использование",
    )

    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
    )

    class Meta:
        verbose_name = "Ключ доступа ССОД"
        verbose_name_plural = "Ключи доступа ССОД"
        ordering = ["user", "-issued_at"]

    def is_currently_active(self):
        now = timezone.now()

        if self.status != self.Status.ACTIVE:
            return False

        if self.expires_at and self.expires_at < now:
            return False

        return True

    def __str__(self):
        return f"{self.user}: {self.name}"

class SystemRole(TimeStampedModel):
    """
    Роль пользователя в системе Auth Center.

    Это не класс доступа (буква S-G) — это человекочитаемая роль:
    Администратор, Оператор, Пользователь и т.д.

    Справочник — администратор добавляет роли через Django Admin
    или через будущий интерфейс управления.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="UUID",
    )

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Название роли",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    class Meta:
        verbose_name = "Роль в системе"
        verbose_name_plural = "Роли в системе"
        ordering = ["name"]

    def __str__(self):
        return self.name
class AuthEvent(TimeStampedModel):
    """
    Журнал событий авторизации.

    Сюда пишем:
    - успешные входы;
    - неуспешные входы;
    - вход по паролю;
    - вход по ключу;
    - блокировки;
    - проверки доступа.

    Это пригодится для безопасности и расследований.
    """

    class EventType(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "Успешный вход"
        LOGIN_FAILED = "login_failed", "Неуспешный вход"
        LOGOUT = "logout", "Выход"
        KEY_LOGIN_SUCCESS = "key_login_success", "Вход по ключу успешен"
        KEY_LOGIN_FAILED = "key_login_failed", "Вход по ключу неуспешен"
        ACCESS_DENIED = "access_denied", "Доступ запрещен"
        ACCESS_GRANTED = "access_granted", "Доступ разрешен"

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="UUID",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auth_events",
        verbose_name="Пользователь",
    )

    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        verbose_name="Тип события",
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP-адрес",
    )

    user_agent = models.TextField(
        blank=True,
        verbose_name="User-Agent",
    )

    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Детали события",
    )

    class Meta:
        verbose_name = "Событие авторизации"
        verbose_name_plural = "События авторизации"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at}: {self.event_type}"

