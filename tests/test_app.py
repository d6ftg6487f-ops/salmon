import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app


class BulbAppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {"TESTING": True, "DATABASE_URL": "sqlite:///:memory:"}
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["bulb_database"].engine.dispose()

    def test_homepage_shows_initial_state(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>豆電球</title>".encode(), response.data)
        self.assertIn("<h1>豆電球</h1>".encode(), response.data)
        self.assertIn("OFF".encode(), response.data)
        self.assertIn(
            "押した回数 <span id=\"count\">0</span> 回".encode(),
            response.data,
        )
        self.assertIn("Firebaseのログイン設定が必要です".encode(), response.data)

    def test_homepage_loads_firebase_login_when_configured(self):
        app = create_app(
            {
                "TESTING": True,
                "DATABASE_URL": "sqlite:///:memory:",
                "FIREBASE_API_KEY": "test-api-key",
                "FIREBASE_AUTH_DOMAIN": "test-project.firebaseapp.com",
                "FIREBASE_PROJECT_ID": "test-project",
                "FIREBASE_APP_ID": "test-app-id",
            }
        )
        try:
            response = app.test_client().get("/")
        finally:
            app.extensions["bulb_database"].engine.dispose()

        self.assertEqual(response.status_code, 200)
        self.assertIn("/static/auth.js".encode(), response.data)
        self.assertIn("test-api-key".encode(), response.data)

    def test_toggle_requires_login(self):
        response = self.client.post("/api/toggle")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "login_required"})
        self.assertEqual(
            self.app.extensions["bulb_database"].get_state(),
            {"is_on": False, "press_count": 0},
        )

    def test_toggle_updates_and_persists_state_and_count(self):
        headers = {"Authorization": "Bearer test-token"}
        with patch(
            "app.firebase_auth.verify_id_token",
            return_value={"uid": "test-user"},
        ):
            first_response = self.client.post("/api/toggle", headers=headers)
            second_response = self.client.post("/api/toggle", headers=headers)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first_response.get_json(), {"is_on": True, "press_count": 1})
        self.assertEqual(second_response.get_json(), {"is_on": False, "press_count": 2})
        self.assertIn(
            "押した回数 <span id=\"count\">2</span> 回".encode(),
            self.client.get("/").data,
        )

    def test_state_survives_database_reinitialization(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory, "bulb.db").as_posix()
            database_url = f"sqlite:///{database_path}"
            first_app = create_app({"DATABASE_URL": database_url})
            with patch(
                "app.firebase_auth.verify_id_token",
                return_value={"uid": "test-user"},
            ):
                first_app.test_client().post(
                    "/api/toggle",
                    headers={"Authorization": "Bearer test-token"},
                )
            first_app.extensions["bulb_database"].engine.dispose()

            second_app = create_app({"DATABASE_URL": database_url})
            response = second_app.test_client().get("/")

            self.assertIn(
                "押した回数 <span id=\"count\">1</span> 回".encode(),
                response.data,
            )
            self.assertIn("ON".encode(), response.data)
            second_app.extensions["bulb_database"].engine.dispose()


if __name__ == "__main__":
    unittest.main()
