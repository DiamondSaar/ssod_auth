import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from accounts.models import Product, UserProductAccess
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
