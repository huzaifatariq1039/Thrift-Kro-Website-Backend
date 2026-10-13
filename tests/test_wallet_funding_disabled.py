import os
import unittest

from fastapi import FastAPI

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers.wallet import router as wallet_router
import app.crud.wallet as wallet_crud


class WalletFundingDisabledTests(unittest.TestCase):
    def test_public_deposit_endpoint_is_not_registered(self):
        app = FastAPI()
        app.include_router(wallet_router, prefix="/wallet")

        paths = app.openapi()["paths"]
        self.assertIn("/wallet/balance", paths)
        self.assertNotIn("/wallet/deposit", paths)

    def test_untrusted_balance_mutation_helper_is_removed(self):
        self.assertFalse(hasattr(wallet_crud, "deposit_funds"))


if __name__ == "__main__":
    unittest.main()
