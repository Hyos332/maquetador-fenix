from app.models.article import Author
from app.services.journal_config import JournalConfigService


def test_author_orcid_is_normalized_once() -> None:
    author = Author(
        full_name="Alberto Nilson",
        orcid="https://orcid.org/0009-0000-5786-8060",
    )

    assert author.orcid == "https://orcid.org/0009-0000-5786-8060"


def test_journal_config_loads_mlshnr_policy() -> None:
    journal = JournalConfigService().load("mlshnr")

    assert journal.key == "mlshnr"
    assert journal.publisher == "Multi Lingual Scientific Journals"
    assert journal.image_style.html_style == "max-width: 700px; max-height: 600px;"
