import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from accounts.models import Organization, Product, UserProductAccess
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
