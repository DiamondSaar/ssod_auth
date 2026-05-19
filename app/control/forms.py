import secrets
import string

from django import forms
from django.contrib.auth import get_user_model

from accounts.models import AccessClass, Organization, Position


def generate_temporary_password(length=12):
    """
    Генерация временного пароля.

    Пароль показываем/отправляем пользователю один раз.
    В базе Django хранит только хэш пароля, не сам пароль.

    Используем secrets, а не random, потому что это пароль,
    а не бросок кубика в настолке.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%"

    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))

        # Небольшая проверка сложности, чтобы пароль не оказался
        # только из букв или только из цифр.
        if (
            any(char.islower() for char in password)
            and any(char.isupper() for char in password)
            and any(char.isdigit() for char in password)
            and any(char in "!@#$%" for char in password)
        ):
            return password


class UserCreateForm(forms.ModelForm):
    """
    Форма создания пользователя в панели управления Auth Center.

    Это не Django Admin форма, а наша рабочая форма.
    Здесь мы контролируем:
    - какие поля показывает интерфейс;
    - какие справочники используются;
    - как валидируются данные;
    - как создается пользователь.
    """

    temporary_password = forms.CharField(
        label="Временный пароль",
        required=False,
        help_text="Можно указать вручную или оставить пустым — система сгенерирует пароль.",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "autocomplete": "new-password",
            }
        ),
    )

    work_email = forms.EmailField(
        label="Рабочая почта",
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "placeholder": "user@example.com",
            }
        ),
    )

    class Meta:
        model = get_user_model()

        fields = [
            "last_name",
            "first_name",
            "middle_name",
            "username",
            "work_email",
            "organization",
            "position",
            "access_class",
            "is_active",
            "temporary_password",
        ]

        labels = {
            "last_name": "Фамилия",
            "first_name": "Имя",
            "middle_name": "Отчество",
            "username": "Логин",
            "organization": "Организация",
            "position": "Должность",
            "access_class": "Класс доступа",
            "is_active": "Активен",
        }

        widgets = {
            "last_name": forms.TextInput(attrs={"class": "form-input"}),
            "first_name": forms.TextInput(attrs={"class": "form-input"}),
            "middle_name": forms.TextInput(attrs={"class": "form-input"}),
            "username": forms.TextInput(attrs={"class": "form-input"}),
            "organization": forms.Select(attrs={"class": "form-input"}),
            "position": forms.Select(attrs={"class": "form-input"}),
            "access_class": forms.Select(attrs={"class": "form-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        """
        Ограничиваем справочники только активными записями.
        """
        super().__init__(*args, **kwargs)

        self.fields["organization"].queryset = Organization.objects.filter(
            is_active=True
        ).order_by("name")

        self.fields["position"].queryset = Position.objects.filter(
            is_active=True
        ).order_by("name")

        self.fields["access_class"].choices = AccessClass.choices

        self.fields["is_active"].initial = True

    def clean_username(self):
        """
        Логин должен быть уникальным.

        Django сам тоже это проверит, но здесь мы дадим более понятную ошибку.
        """
        username = self.cleaned_data["username"].strip()

        User = get_user_model()

        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Пользователь с таким логином уже существует.")

        return username

    def save(self, commit=True):
        """
        Создание пользователя.

        Важное:
        - пароль сохраняем через set_password;
        - в БД не хранится исходный пароль;
        - must_change_password=True заставит потом сменить пароль.
        """
        user = super().save(commit=False)

        temporary_password = self.cleaned_data.get("temporary_password")

        if not temporary_password:
            temporary_password = generate_temporary_password()

        user.email = self.cleaned_data["work_email"]
        user.must_change_password = True
        user.set_password(temporary_password)

        if commit:
            user.save()

        # Сохраняем временный пароль только в объекте формы,
        # чтобы после создания отправить его по почте.
        # В БД он НЕ пишется.
        self.generated_password = temporary_password

        return user
