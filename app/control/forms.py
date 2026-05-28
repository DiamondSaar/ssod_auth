import secrets
import string

from django import forms
from django.contrib.auth import get_user_model

from accounts.models import AccessClass, Organization, Position, SystemRole


def generate_temporary_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%" for c in password)
        ):
            return password


class UserCreateForm(forms.ModelForm):
    temporary_password = forms.CharField(
        label="Временный пароль",
        required=False,
        help_text="Оставьте пустым — система сгенерирует пароль.",
        widget=forms.TextInput(attrs={"class": "form-input", "autocomplete": "new-password"}),
    )

    work_email = forms.EmailField(
        label="Рабочая почта",
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-input"}),
    )

    class Meta:
        model = get_user_model()
        fields = [
            "last_name", "first_name", "middle_name",
            "username", "work_email",
            "organization", "position", "system_role",
            "access_class", "is_active", "temporary_password",
        ]
        labels = {
            "last_name": "Фамилия",
            "first_name": "Имя",
            "middle_name": "Отчество",
            "username": "Логин",
            "organization": "Организация",
            "position": "Должность",
            "system_role": "Роль в системе",
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
            "system_role": forms.Select(attrs={"class": "form-input"}),
            "access_class": forms.Select(attrs={"class": "form-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = Organization.objects.filter(is_active=True).order_by("name")
        self.fields["position"].queryset = Position.objects.filter(is_active=True).order_by("name")
        self.fields["system_role"].queryset = SystemRole.objects.filter(is_active=True).order_by("name")
        self.fields["system_role"].required = False
        self.fields["access_class"].choices = AccessClass.choices
        self.fields["is_active"].initial = True

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        User = get_user_model()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Пользователь с таким логином уже существует.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        temporary_password = self.cleaned_data.get("temporary_password") or generate_temporary_password()
        user.email = self.cleaned_data["work_email"]
        user.must_change_password = True
        user.set_password(temporary_password)
        if commit:
            user.save()
        self.generated_password = temporary_password
        return user


class UserEditForm(forms.ModelForm):
    """
    Форма редактирования существующего пользователя.

    Отличия от формы создания:
    - нет поля пароля (пароль сбрасывается отдельной кнопкой)
    - есть поля аватара, даты рождения, комментариев
    - логин можно менять но проверяем уникальность исключая текущего пользователя
    """

    class Meta:
        model = get_user_model()
        fields = [
            "last_name", "first_name", "middle_name",
            "username", "email",
            "birth_date", "avatar",
            "organization", "position", "system_role",
            "access_class", "is_active",
            "public_comment", "admin_comment",
        ]
        labels = {
            "last_name": "Фамилия",
            "first_name": "Имя",
            "middle_name": "Отчество",
            "username": "Логин",
            "email": "Email",
            "birth_date": "Дата рождения",
            "avatar": "Аватар",
            "organization": "Организация",
            "position": "Должность",
            "system_role": "Роль в системе",
            "access_class": "Класс доступа",
            "is_active": "Активен",
            "public_comment": "Комментарий для пользователя",
            "admin_comment": "Комментарий администратора",
        }
        widgets = {
            "last_name": forms.TextInput(attrs={"class": "form-input"}),
            "first_name": forms.TextInput(attrs={"class": "form-input"}),
            "middle_name": forms.TextInput(attrs={"class": "form-input"}),
            "username": forms.TextInput(attrs={"class": "form-input"}),
            "email": forms.EmailInput(attrs={"class": "form-input"}),
            "birth_date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "organization": forms.Select(attrs={"class": "form-input"}),
            "position": forms.Select(attrs={"class": "form-input"}),
            "system_role": forms.Select(attrs={"class": "form-input"}),
            "access_class": forms.Select(attrs={"class": "form-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "public_comment": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
            "admin_comment": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = Organization.objects.filter(is_active=True).order_by("name")
        self.fields["organization"].required = False
        self.fields["position"].queryset = Position.objects.filter(is_active=True).order_by("name")
        self.fields["position"].required = False
        self.fields["system_role"].queryset = SystemRole.objects.filter(is_active=True).order_by("name")
        self.fields["system_role"].required = False
        self.fields["avatar"].required = False

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        User = get_user_model()
        # Исключаем текущего пользователя из проверки уникальности
        qs = User.objects.filter(username__iexact=username)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Пользователь с таким логином уже существует.")
        return username