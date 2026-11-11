import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import jwt
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django_otp import DEVICE_ID_SESSION_KEY

from accounts.models import Organization, Product, ProductRole, UserProductAccess
from accounts.services.dominex_sync import apply_projection


# Каталог app/ — в нём лежат templates/ всех приложений проекта.
APP_ROOT = Path(__file__).resolve().parent.parent

# Открытый {# без закрывающего #} на той же строке.
UNCLOSED_COMMENT = re.compile(r"\{#(?!.*#\})")


class TemplateCommentTests(SimpleTestCase):
    """
    Однострочный комментарий Django {# ... #} работает только в пределах
    одной строки. Если его перенести, Django выводит текст комментария
    прямо на страницу — так на экран входа попала служебная пометка.
    Многострочные комментарии пишутся через {% comment %}...{% endcomment %}.
    """

    def test_no_multiline_hash_comments(self):
        offenders = []

        for template in APP_ROOT.rglob("templates/**/*.html"):
            lines = template.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines, start=1):
                if UNCLOSED_COMMENT.search(line):
                    offenders.append(f"{template.relative_to(APP_ROOT)}:{number}")

        self.assertEqual(
            offenders,
            [],
            "Перенесённый {# ... #} выводится на страницу как текст — "
            "замените на {% comment %}...{% endcomment %}",
        )


def _projection(url=None):
    product = {
        "grant_id": 1,
        "code": "vox",
        "name": "Dominex Vox",
        "status": "active",
        "access_class": "G",
    }
    if url is not None:
        product["url"] = url

    return {
        "access_class": "F",
        "organization": {"id": 1, "name": "ООО Тест", "inn": ""},
        "products": [product],
    }


class ApplyProjectionProductUrlTests(TestCase):
    """
    Продукт, впервые пришедший из Dominex через грант, раньше заводился без
    адреса, и его карточка в «Мои продукты» никуда не вела (Dominex Vox,
    2026-09-14). Адрес берётся из проекции, но свой адрес не перетирается.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="projection-user", password="x")

    def test_new_product_gets_url_from_projection(self):
        apply_projection(self.user, _projection(url="https://khalisida.com:8444"))

        self.assertEqual(Product.objects.get(code="vox").product_url, "https://khalisida.com:8444")

    def test_empty_local_url_is_filled(self):
        Product.objects.create(code="vox", name="Dominex Vox", product_url="")

        apply_projection(self.user, _projection(url="https://khalisida.com:8444"))

        self.assertEqual(Product.objects.get(code="vox").product_url, "https://khalisida.com:8444")

    def test_local_url_is_not_overwritten(self):
        Product.objects.create(code="vox", name="Dominex Vox", product_url="https://vox.example/")

        apply_projection(self.user, _projection(url="https://khalisida.com:8444"))

        self.assertEqual(Product.objects.get(code="vox").product_url, "https://vox.example/")

    def test_projection_without_url_still_syncs(self):
        # Старый Dominex, ещё не отдающий url, не должен ломать синхронизацию.
        apply_projection(self.user, _projection())

        product = Product.objects.get(code="vox")
        self.assertEqual(product.product_url, "")
        self.assertTrue(UserProductAccess.objects.filter(user=self.user, product=product).exists())


class OrganizationCabinetTests(TestCase):
    """
    Кабинет юрлица — отдельная зона. Обезличенная учётная запись
    организации не должна попадать в личные разделы, а обычный
    пользователь — в кабинет юрлица.
    """

    def setUp(self):
        User = get_user_model()
        self.organization = Organization.objects.create(name="АсКомпонент")

        self.org_user = User.objects.create_user(username="ascom-lk", password="x")
        self.org_user.organization = self.organization
        self.org_user.is_organization_account = True
        self.org_user.save()

        self.person = User.objects.create_user(username="ivanov", password="x")

    def test_org_account_is_sent_from_personal_cabinet_to_its_own(self):
        self.client.force_login(self.org_user)

        response = self.client.get("/account/")

        self.assertRedirects(response, "/account/org/", fetch_redirect_response=False)

    def test_org_account_is_sent_away_from_personal_sections(self):
        self.client.force_login(self.org_user)

        for path in ("/account/products/", "/account/security/", "/account/repository/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertRedirects(response, "/account/org/", fetch_redirect_response=False)

    def test_org_pages_open_for_org_account(self):
        self.client.force_login(self.org_user)

        for path in ("/account/org/documents/", "/account/org/contact/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_org_cabinet_hidden_from_personal_account(self):
        self.client.force_login(self.person)

        for path in ("/account/org/", "/account/org/documents/", "/account/org/contact/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_personal_account_is_not_redirected(self):
        self.client.force_login(self.person)

        self.assertEqual(self.client.get("/account/products/").status_code, 200)


class MailSystemsTests(TestCase):
    """
    «Почтовые системы» — внутренний раздел ССОД: две ссылки на вход в
    почту. Пользователю чужой организации плитка не нужна (войти он туда
    всё равно не сможет), поэтому раздел закрыт и в кабинете не виден.
    """

    def setUp(self):
        User = get_user_model()
        self.ssod = Organization.objects.create(name="ССОД-тест", inn="7716259720")
        self.client_org = Organization.objects.create(name="Клиент-тест", inn="1234567890")

        # must_change_password по умолчанию включён и уводит с главной
        # кабинета на смену пароля — здесь проверяется не он.
        self.ours = User.objects.create_user(username="ssod-user", password="x")
        self.ours.organization = self.ssod
        self.ours.must_change_password = False
        self.ours.save()

        self.theirs = User.objects.create_user(username="client-user", password="x")
        self.theirs.organization = self.client_org
        self.theirs.must_change_password = False
        self.theirs.save()

        self.staff = User.objects.create_user(username="staffer", password="x", is_staff=True)
        self.staff.must_change_password = False
        self.staff.save()

    def test_page_opens_for_our_organization(self):
        self.client.force_login(self.ours)

        response = self.client.get("/account/mail/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://mail.ssod.pro/")
        self.assertContains(response, "https://webmail.hosting.reg.ru/")

    def test_page_opens_for_staff_without_organization(self):
        self.client.force_login(self.staff)

        self.assertEqual(self.client.get("/account/mail/").status_code, 200)

    def test_page_hidden_from_other_organization(self):
        self.client.force_login(self.theirs)

        self.assertEqual(self.client.get("/account/mail/").status_code, 404)

    def test_tile_shown_only_to_us(self):
        self.client.force_login(self.ours)
        self.assertContains(self.client.get("/account/"), "Почтовые системы")

        self.client.force_login(self.theirs)
        self.assertNotContains(self.client.get("/account/"), "Почтовые системы")


def _add_key(user, name="YubiKey"):
    from django_otp_webauthn.models import WebAuthnCredential

    seed = f"{user.username}-{name}".encode()
    return WebAuthnCredential.objects.create(
        user=user,
        name=name,
        confirmed=True,
        credential_id=seed,
        public_key=b"test-public-key",
        aaguid="00000000-0000-0000-0000-000000000000",
        credential_id_sha256=hashlib.sha256(seed).hexdigest(),
    )


@override_settings(ADMIN_SECOND_FACTOR="soft")
class AdminSecondFactorTests(TestCase):
    """
    Решение владельца 11.11.2026: админский доступ всегда подтверждается
    аппаратным ключом, пользователи без админских прав входят паролем.
    """

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username="adm", password="x")
        self.admin.dominex_role = "superadmin"
        self.admin.must_change_password = False
        self.admin.save()

        self.person = User.objects.create_user(username="person", password="x")
        self.person.dominex_role = "user"
        self.person.must_change_password = False
        self.person.save()

    def _verify_with(self, key):
        # То же, что делает django_otp.login() после проверки ключа.
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = key.persistent_id
        session.save()

    def test_role_comes_from_projection(self):
        projection = _projection()
        projection["role"] = "admin"

        apply_projection(self.person, projection)

        self.person.refresh_from_db()
        self.assertEqual(self.person.dominex_role, "admin")

    def test_user_without_admin_rights_is_not_asked(self):
        _add_key(self.person)
        self.client.force_login(self.person)

        self.assertEqual(self.client.get("/account/products/").status_code, 200)

    def test_admin_with_key_must_confirm_it(self):
        _add_key(self.admin)
        self.client.force_login(self.admin)

        response = self.client.get("/account/products/")

        self.assertRedirects(
            response, "/account/login/key/?next=%2Faccount%2Fproducts%2F", fetch_redirect_response=False
        )
        self.assertEqual(self.client.get("/account/login/key/").status_code, 200)

    def test_admin_confirmed_by_key_passes(self):
        key = _add_key(self.admin)
        self.client.force_login(self.admin)
        self._verify_with(key)

        self.assertEqual(self.client.get("/account/products/").status_code, 200)

    def test_staff_counts_as_admin(self):
        self.person.is_staff = True
        self.person.save()
        _add_key(self.person)
        self.client.force_login(self.person)

        self.assertEqual(self.client.get("/account/products/").status_code, 302)

    def test_soft_mode_admin_without_key_is_asked_to_add_one(self):
        self.client.force_login(self.admin)

        response = self.client.get("/account/products/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Добавьте ключ")

    @override_settings(ADMIN_SECOND_FACTOR="strict")
    def test_strict_mode_admin_without_key_is_logged_out(self):
        self.client.force_login(self.admin)

        response = self.client.get("/account/products/")

        self.assertRedirects(response, "/account/login/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(ADMIN_SECOND_FACTOR="off")
    def test_off_mode_skips_the_check(self):
        _add_key(self.admin)
        self.client.force_login(self.admin)

        self.assertEqual(self.client.get("/account/products/").status_code, 200)

    def test_last_key_of_admin_cannot_be_deleted(self):
        key = _add_key(self.admin)
        self.client.force_login(self.admin)
        self._verify_with(key)

        self.client.post(f"/account/security/keys/{key.pk}/delete/")

        self.assertTrue(type(key).objects.filter(pk=key.pk).exists())

    def test_spare_key_can_be_deleted_from_confirmed_session(self):
        key = _add_key(self.admin, "Основной")
        spare = _add_key(self.admin, "Запасной")
        self.client.force_login(self.admin)
        self._verify_with(key)

        self.client.post(f"/account/security/keys/{spare.pk}/delete/")

        self.assertFalse(type(spare).objects.filter(pk=spare.pk).exists())

    def test_keys_cannot_be_removed_by_password_alone(self):
        # Пользователь без админских прав с ключом, вошедший паролем:
        # узнавший пароль не должен снять ключ.
        key = _add_key(self.person, "Основной")
        _add_key(self.person, "Запасной")
        self.client.force_login(self.person)

        self.client.post(f"/account/security/keys/{key.pk}/delete/")

        self.assertTrue(type(key).objects.filter(pk=key.pk).exists())

    def _ticket_for(self, user, key=None):
        product = Product.objects.create(code="dominex", name="Dominex", sso_enabled=True,
                                         product_url="https://dominex.example")
        organization = Organization.objects.create(name="ССОД-тест")
        role = ProductRole.objects.create(product=product, code="r", name="r")
        UserProductAccess.objects.create(user=user, product=product, organization=organization,
                                         role=role, status=UserProductAccess.Status.ACTIVE)
        self.client.force_login(user)
        if key:
            self._verify_with(key)

        response = self.client.get("/account/sso/authorize/dominex/")
        self.assertEqual(response.status_code, 302, response)
        ticket = parse_qs(urlparse(response["Location"]).query)["ticket"][0]
        return jwt.decode(ticket, options={"verify_signature": False})

    def test_ticket_marks_key_confirmed_login(self):
        key = _add_key(self.admin)

        self.assertEqual(self._ticket_for(self.admin, key)["amr"], ["hwk"])

    def test_ticket_marks_password_only_login(self):
        self.assertEqual(self._ticket_for(self.person)["amr"], ["pwd"])
