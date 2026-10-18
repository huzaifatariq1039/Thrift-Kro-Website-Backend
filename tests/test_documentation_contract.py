import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _word_document_xml() -> str:
    document = PROJECT_ROOT / "Thrift_Kro_Backend_Documentation.docx"
    with zipfile.ZipFile(document) as archive:
        return archive.read("word/document.xml").decode("utf-8")


class DocumentationContractTests(unittest.TestCase):
    def test_backend_readme_names_current_schema_and_commerce_contracts(self):
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        for statement in (
            "Alembic as the only schema authority",
            "CheckoutOrder",
            "SellerOrder",
            "5 percent platform fee",
            "PKR 200 shipping",
            "Card checkout remains unavailable",
            "AI product verification and virtual try-on are not approved",
        ):
            with self.subTest(statement=statement):
                self.assertIn(statement, readme)

        self.assertNotIn("admin123", readme)
        self.assertNotIn("Base.metadata.create_all(bind=engine)", readme)

    def test_word_guide_replaces_obsolete_release_claims(self):
        document_xml = _word_document_xml()

        for statement in (
            "Current Implementation Guide",
            "20261018_15",
            "CheckoutOrder",
            "SellerOrder",
            "5 percent",
            "PKR 200",
            "Card payments are unavailable",
            "AI product verification is not available",
        ):
            with self.subTest(statement=statement):
                self.assertIn(statement, document_xml)

        for obsolete in (
            "Production Release Documentation",
            "escrow_fee = subtotal * 0.02",
            "shipping_fee = 100 PKR",
            "admin@thriftkro.com / admin123",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, document_xml)


if __name__ == "__main__":
    unittest.main()
