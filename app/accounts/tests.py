import re
from pathlib import Path

from django.test import SimpleTestCase


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
