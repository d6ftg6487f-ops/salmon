import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import create_app


class FakeRecaptchaClient:
    def __init__(self, valid=True, action=None):
        self.valid = valid
        self.action = action
        self.requests = []

    def create_assessment(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            token_properties=SimpleNamespace(
                valid=self.valid,
                action=self.action or request.assessment.event.expected_action,
                invalid_reason="INVALID_TOKEN" if not self.valid else None,
            )
        )


class BulbAppTests(unittest.TestCase):
    def setUp(self):
        self.recaptcha_client = FakeRecaptchaClient()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE_URL": "sqlite:///:memory:",
                "RECAPTCHA_PROJECT_ID": "test-project",
                "RECAPTCHA_CLIENT": self.recaptcha_client,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["bulb_database"].engine.dispose()

    def enter_site(self, client=None, token="entry-token"):
        client = client or self.client
        return client.post("/api/site-entry", json={"recaptcha_token": token})

    def test_homepage_requires_one_site_entry_recaptcha(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "下のチェックボックスで確認を完了してから".encode(),
            response.data,
        )
        self.assertIn("enterprise.js".encode(), response.data)
        self.assertIn('id="site-entry-captcha"'.encode(), response.data)
        self.assertIn("recaptcha.js".encode(), response.data)
        self.assertNotIn("chat-form".encode(), response.data)
        self.assertNotIn('id="toggle"'.encode(), response.data)

        entry_response = self.enter_site()
        self.assertEqual(entry_response.status_code, 200)
        self.assertEqual(entry_response.get_json(), {"success": True})

        app_response = self.client.get("/")
        self.assertIn("<title>豆電球</title>".encode(), app_response.data)
        self.assertIn("豆電球に質問".encode(), app_response.data)
        self.assertIn("chat.js".encode(), app_response.data)
        self.assertNotIn("enterprise.js".encode(), app_response.data)
        self.assertNotIn("g-recaptcha".encode(), app_response.data)

    def test_static_frontend_files_are_used_when_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            entry_path = Path(directory) / "entry.html"
            index_path = Path(directory) / "index.html"
            entry_path.write_text("<html>entry static</html>", encoding="utf-8")
            index_path.write_text("<html>index static</html>", encoding="utf-8")

            app = create_app(
                {
                    "TESTING": True,
                    "SECRET_KEY": "test-secret",
                    "DATABASE_URL": "sqlite:///:memory:",
                    "FRONTEND_DIST_DIR": directory,
                    "RECAPTCHA_PROJECT_ID": "test-project",
                    "RECAPTCHA_CLIENT": FakeRecaptchaClient(),
                }
            )
            try:
                client = app.test_client()
                self.assertIn(b"entry static", client.get("/").data)

                with client.session_transaction() as session:
                    session["site_verified"] = True

                self.assertIn(b"index static", client.get("/").data)
            finally:
                app.extensions["bulb_database"].engine.dispose()

    def test_api_operations_are_blocked_until_site_entry(self):
        toggle_response = self.client.post("/api/toggle")
        chat_response = self.client.post("/api/chat", json={"message": "質問"})

        self.assertEqual(toggle_response.status_code, 403)
        self.assertEqual(chat_response.status_code, 403)
        self.assertEqual(
            self.app.extensions["bulb_database"].get_state(),
            {"is_on": False, "press_count": 0},
        )
        self.assertEqual(self.recaptcha_client.requests, [])

    def test_cloud_run_session_key_is_derived_from_existing_db_secret(self):
        with patch.dict(
            "os.environ",
            {"K_SERVICE": "test", "DB_PASSWORD": "stable-db-password", "FLASK_SECRET_KEY": ""},
        ):
            first_app = create_app({"DATABASE_URL": "sqlite:///:memory:"})
            second_app = create_app({"DATABASE_URL": "sqlite:///:memory:"})
            try:
                self.assertTrue(first_app.config["SESSION_COOKIE_SECURE"])
                self.assertEqual(
                    first_app.config["SECRET_KEY"],
                    second_app.config["SECRET_KEY"],
                )
                self.assertTrue(first_app.config["SECRET_KEY"])
            finally:
                first_app.extensions["bulb_database"].engine.dispose()
                second_app.extensions["bulb_database"].engine.dispose()

    def test_cloud_run_requires_a_stable_session_secret(self):
        with patch.dict(
            "os.environ",
            {"K_SERVICE": "test", "DB_PASSWORD": "", "FLASK_SECRET_KEY": ""},
        ):
            with self.assertRaisesRegex(RuntimeError, "FLASK_SECRET_KEY or DB_PASSWORD"):
                create_app({"DATABASE_URL": "sqlite:///:memory:"})

    def test_toggle_updates_and_persists_state_after_single_site_check(self):
        self.assertEqual(self.enter_site().status_code, 200)
        first_response = self.client.post("/api/toggle")
        second_response = self.client.post("/api/toggle")

        self.assertEqual(first_response.get_json(), {"is_on": True, "press_count": 1})
        self.assertEqual(second_response.get_json(), {"is_on": False, "press_count": 2})
        self.assertEqual(len(self.recaptcha_client.requests), 1)
        self.assertEqual(
            self.recaptcha_client.requests[0].assessment.event.expected_action,
            "SITE_ENTRY",
        )
        self.assertIn(
            "押した回数 <span id=\"count\">2</span> 回".encode(),
            self.client.get("/").data,
        )

    def test_state_survives_database_reinitialization(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory, "bulb.db").as_posix()
            database_url = f"sqlite:///{database_path}"
            first_app = create_app(
                {
                    "SECRET_KEY": "test-secret",
                    "DATABASE_URL": database_url,
                    "RECAPTCHA_PROJECT_ID": "test-project",
                    "RECAPTCHA_CLIENT": FakeRecaptchaClient(),
                }
            )
            first_client = first_app.test_client()
            first_client.post(
                "/api/site-entry", json={"recaptcha_token": "entry-token"}
            )
            first_client.post("/api/toggle")
            first_app.extensions["bulb_database"].engine.dispose()

            second_app = create_app(
                {
                    "SECRET_KEY": "test-secret",
                    "DATABASE_URL": database_url,
                    "RECAPTCHA_PROJECT_ID": "test-project",
                    "RECAPTCHA_CLIENT": FakeRecaptchaClient(),
                }
            )
            second_client = second_app.test_client()
            second_client.get("/")
            second_client.post(
                "/api/site-entry", json={"recaptcha_token": "entry-token"}
            )
            response = second_client.get("/")

            self.assertIn(
                "押した回数 <span id=\"count\">1</span> 回".encode(),
                response.data,
            )
            self.assertIn("ON".encode(), response.data)
            second_app.extensions["bulb_database"].engine.dispose()

    def test_chat_returns_vertex_response_and_limits_generated_tokens(self):
        class FakeModels:
            def generate_content(self, **kwargs):
                self.request = kwargs
                return type("Response", (), {"text": "電球はボタンで消せます。"})()

        class FakeClient:
            def __init__(self):
                self.models = FakeModels()

        fake_client = FakeClient()
        recaptcha_client = FakeRecaptchaClient()
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE_URL": "sqlite:///:memory:",
                "VERTEX_CLIENT": fake_client,
                "RECAPTCHA_PROJECT_ID": "test-project",
                "RECAPTCHA_CLIENT": recaptcha_client,
            }
        )
        try:
            client = app.test_client()
            entry_response = client.post(
                "/api/site-entry", json={"recaptcha_token": "entry-token"}
            )
            response = client.post(
                "/api/chat",
                json={
                    "message": "消し方は？",
                    "history": [{"role": "user", "text": "こんにちは"}],
                },
            )

            self.assertEqual(entry_response.status_code, 200)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"answer": "電球はボタンで消せます。"})
            self.assertEqual(
                fake_client.models.request["model"],
                "gemini-3.1-flash-lite",
            )
            self.assertEqual(
                fake_client.models.request["config"].max_output_tokens,
                256,
            )
            self.assertEqual(
                fake_client.models.request["config"].thinking_config.thinking_level.value,
                "MINIMAL",
            )
            self.assertEqual(len(recaptcha_client.requests), 1)
            self.assertEqual(
                recaptcha_client.requests[0].assessment.event.expected_action,
                "SITE_ENTRY",
            )
        finally:
            app.extensions["bulb_database"].engine.dispose()

    def test_chat_rejects_invalid_or_oversized_input(self):
        self.enter_site()
        response = self.client.post("/api/chat", json={"message": "質問", "history": "bad"})
        self.assertEqual(response.status_code, 400)

        response = self.client.post("/api/chat", json={"message": "あ" * 1001})
        self.assertEqual(response.status_code, 400)

    def test_chat_requires_vertex_project_configuration(self):
        self.enter_site()
        response = self.client.post(
            "/api/chat", json={"message": "電球の消し方"}
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json(),
            {"error": "チャット機能の設定が完了していません。"},
        )

    def test_site_entry_rejects_missing_invalid_or_mismatched_captcha(self):
        missing_token_response = self.client.post("/api/site-entry", json={})
        self.assertEqual(missing_token_response.status_code, 400)

        invalid_app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE_URL": "sqlite:///:memory:",
                "RECAPTCHA_PROJECT_ID": "test-project",
                "RECAPTCHA_CLIENT": FakeRecaptchaClient(valid=False),
            }
        )
        try:
            invalid_client = invalid_app.test_client()
            response = invalid_client.post(
                "/api/site-entry", json={"recaptcha_token": "invalid-token"}
            )
            self.assertEqual(response.status_code, 403)
            self.assertIn(
                "下のチェックボックスで確認を完了してから".encode(),
                invalid_client.get("/").data,
            )
        finally:
            invalid_app.extensions["bulb_database"].engine.dispose()

        mismatched_app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE_URL": "sqlite:///:memory:",
                "RECAPTCHA_PROJECT_ID": "test-project",
                "RECAPTCHA_CLIENT": FakeRecaptchaClient(action="CHAT"),
            }
        )
        try:
            response = mismatched_app.test_client().post(
                "/api/site-entry", json={"recaptcha_token": "mismatched-token"}
            )
            self.assertEqual(response.status_code, 403)
        finally:
            mismatched_app.extensions["bulb_database"].engine.dispose()

    def test_site_entry_requires_project_configuration(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE_URL": "sqlite:///:memory:",
                "RECAPTCHA_CLIENT": FakeRecaptchaClient(),
            }
        )
        try:
            response = app.test_client().post(
                "/api/site-entry", json={"recaptcha_token": "entry-token"}
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(
                response.get_json(),
                {"error": "reCAPTCHA の設定が完了していません。"},
            )
        finally:
            app.extensions["bulb_database"].engine.dispose()


if __name__ == "__main__":
    unittest.main()

