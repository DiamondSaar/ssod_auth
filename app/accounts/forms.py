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


class ServiceClientCreateForm(forms.Form):
    """
    Регистрация нового машинного клиента (модуля экосистемы) для
    межсервисной (машина-машина) авторизации - см. accounts.api.
    issue_service_token и dominex/docs/module-interactions.md,
    "Service-to-service auth for new modules".
    """

    code = forms.SlugField(
        label="Код клиента",
        max_length=100,
        help_text="Например: atb_portal - используется модулем как client_id",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "atb_portal",
            }
        ),
    )

    name = forms.CharField(
        label="Название",
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "ATB Portal",
            }
        ),
    )


class ServiceClientGrantCreateForm(forms.Form):
    """Разрешение уже существующему ServiceClient запрашивать токен на
    конкретный audience (код целевого сервиса, например "dominex")."""

    audience = forms.SlugField(
        label="Audience (целевой сервис)",
        max_length=100,
        help_text="Например: dominex",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "dominex",
            }
        ),
    )


def _txt(placeholder="", required=True):
    return forms.CharField(
        required=required,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": placeholder}),
    )


def _secret(placeholder="", required=True):
    return forms.CharField(
        required=required,
        widget=forms.PasswordInput(attrs={"class": "form-input", "placeholder": placeholder}, render_value=True),
    )


class PortalDeployForm(forms.Form):
    """Форма развёртывания нового портала на удалённой VM из консоли ССОД.
    Собирает SSH-реквизиты целевой VM + организационный конфиг портала.
    Секреты (SECRET_KEY/пароль БД/Fernet/ServiceClient-секрет) НЕ в форме -
    генерируются на сервере. SSH-креды в БД не сохраняются (см. DeployJob)."""

    # ── Целевая VM (SSH) ──
    org_code = forms.SlugField(
        label="Код организации",
        max_length=100,
        help_text="латиницей, напр. ascom - станет ascom_portal / ascom_ad",
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "ascom"}),
    )
    target_host = _txt("95.64.129.54")
    target_port = forms.IntegerField(
        initial=22, min_value=1, max_value=65535,
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    target_user = _txt("ascom")
    auth_method = forms.ChoiceField(
        choices=[("password", "Пароль"), ("key", "Приватный SSH-ключ")],
        widget=forms.RadioSelect,
        initial="password",
    )
    ssh_password = _secret("пароль SSH", required=False)
    ssh_private_key = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-input", "rows": 6, "placeholder": "-----BEGIN OPENSSH PRIVATE KEY-----"}),
    )
    ssh_key_passphrase = _secret("пароль ключа (если есть)", required=False)
    sudo_password = _secret("sudo-пароль (если требуется)", required=False)

    # ── Конфиг портала (.env) ──
    portal_title = _txt("AsCom VPN Portal")
    portal_org_name = _txt("АсКом")
    portal_base_url = _txt("https://vpn.ascom.local")

    ldap_server = _txt("ascom.local")
    ldap_base_dn = _txt("DC=ascom,DC=local")
    ldap_bind_user = _txt("CN=ldap_reader,CN=Users,DC=ascom,DC=local")
    ldap_bind_password = _secret("пароль ldap_reader")
    ldap_admin_group = _txt("CN=VPN_ADMINS,CN=Users,DC=ascom,DC=local")
    vpn_group_admins = _txt("ACCESS_ADMIN")
    vpn_group_users = _txt("ACCESS_RDS")

    opnsense_host = _txt("https://10.0.0.1", required=False)
    opnsense_api_key = _secret("OPNsense API key", required=False)
    opnsense_api_secret = _secret("OPNsense API secret", required=False)
    opnsense_ca_ref = _txt("caref", required=False)
    ovpn_server_admins_uuid = _txt("", required=False)
    ovpn_server_users_uuid = _txt("", required=False)
    wg_server_admins_uuid = _txt("", required=False)
    wg_server_users_uuid = _txt("", required=False)

    winrm_host = _txt("", required=False)
    winrm_user = _txt("", required=False)
    winrm_password = _secret("", required=False)

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("auth_method")
        if method == "password" and not cleaned.get("ssh_password"):
            self.add_error("ssh_password", "Укажите SSH-пароль или выберите вход по ключу.")
        if method == "key" and not cleaned.get("ssh_private_key"):
            self.add_error("ssh_private_key", "Вставьте приватный ключ или выберите вход по паролю.")
        return cleaned
