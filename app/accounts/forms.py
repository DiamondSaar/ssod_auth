from django import forms
from django.contrib.auth.password_validation import validate_password


class FirstPasswordChangeForm(forms.Form):
    """
    Форма первой смены пароля.

    Старый пароль не спрашиваем:
    пользователь уже подтвердил его при входе.
    """

    new_password1 = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "autocomplete": "new-password",
            }
        ),
    )

    new_password2 = forms.CharField(
        label="Повторите новый пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean_new_password1(self):
        password = self.cleaned_data["new_password1"]
        validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()

        password1 = cleaned_data.get("new_password1")
        password2 = cleaned_data.get("new_password2")

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Пароли не совпадают.")

        return cleaned_data


class SSODAccessKeyCreateForm(forms.Form):
    """
    Форма выпуска ключа доступа ССОД.

    На первом этапе ключ — это внутренний технический секрет.
    Позже сюда можно добавить загрузку публичного ключа/сертификата.
    """

    name = forms.CharField(
        label="Название ключа",
        max_length=255,
        help_text="Например: Рабочий ноутбук, Домашний ПК, Тестовый ключ",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Рабочий ноутбук",
            }
        ),
    )
