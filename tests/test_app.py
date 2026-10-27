import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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
                "DATABASE_URL": "sqlite:///:memory:",
                "RECAPTCHA_PROJECT_ID": "test-project",
                "RECAPTCHA_CLIENT": self.recaptcha_client,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["bulb_database"].engine.dispose()

    def test_homepage_shows_initial_state(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>豆電球</title>".encode(), response.data)
        self.assertIn("<h1>豆電球</h1>".encode(), response.data)
        self.assertIn("豆電球に質問".encode(), response.data)
        self.assertIn("chat.js".encode(), response.data)
        self.assertIn("recaptcha.js".encode(), response.data)
        self.assertIn("enterprise.js".encode(), response.data)
        self.assertIn('data-action="CHAT"'.encode(), response.data)
        self.assertIn('data-action="TOGGLE"'.encode(), response.data)
        self.assertIn("OFF".encode(), response.data)
        self.assertIn(
            "押した回数 <span id=\"count\">0</span> 回".encode(),
            response.data,
        )

    def test_toggle_updates_and_persists_state_and_count(self):
        first_response = self.client.post(
            "/api/toggle", json={"recaptcha_token": "toggle-token"}
        )
        second_response = self.client.post(
            "/api/toggle", json={"recaptcha_token": "toggle-token-2"}
        )

        self.assertEqual(first_response.get_json(), {"is_on": True, "press_count": 1})
        self.assertEqual(second_response.get_json(), {"is_on": False, "press_count": 2})
        self.assertEqual(
            [
                request.assessment.event.expected_action
                for request in self.recaptcha_client.requests
            ],
            ["TOGGLE", "TOGGLE"],
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
                    "DATABASE_URL": database_url,
                    "RECAPTCHA_PROJECT_ID": "test-project",
                    "RECAPTCHA_CLIENT": FakeRecaptchaClient(),
                }
            )
            first_app.test_client().post(
                "/api/toggle", json={"recaptcha_token": "toggle-token"}
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
                "DATABASE_URL": "sqlite:///:memory:",
                "VERTEX_CLIENT": fake_client,
                "RECAPTCHA_PROJECT_ID": "test-project",
                "RECAPTCHA_CLIENT": recaptcha_client,
            }
        )
        try:
            client = app.test_client()
            response = client.post(
                "/api/chat",
                json={
                    "message": "消し方は？",
                    "history": [{"role": "user", "text": "こんにちは"}],
                    "recaptcha_token": "chat-token",
                },
            )

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
            self.assertEqual(
                recaptcha_client.requests[0].assessment.event.expected_action,
                "CHAT",
            )
        finally:
            app.extensions["bulb_database"].engine.dispose()

    def test_chat_rejects_invalid_or_oversized_input(self):
        response = self.client.post(
            "/api/chat",
            json={
                "message": "質問",
                "history": "bad",
                "recaptcha_token": "chat-token",
            },
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/chat",
            json={"message": "あ" * 1001, "recaptcha_token": "chat-token"},
        )
        self.assertEqual(response.status_code, 400)

    def test_chat_requires_vertex_project_configuration(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "電球の消し方", "recaptcha_token": "chat-token"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json(),
            {"error": "チャット機能の設定が完了していません。"},
        )

    def test_toggle_rejects_missing_or_invalid_recaptcha(self):
        missing_token_response = self.client.post("/api/toggle", json={})
        self.assertEqual(missing_token_response.status_code, 400)

        invalid_app = create_app(
            {
                "TESTING": True,
                "DATABASE_URL": "sqlite:///:memory:",
                "RECAPTCHA_PROJECT_ID": "test-project",
                "RECAPTCHA_CLIENT": FakeRecaptchaClient(valid=False),
            }
        )
        try:
            response = invalid_app.test_client().post(
                "/api/toggle", json={"recaptcha_token": "invalid-token"}
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(
                invalid_app.extensions["bulb_database"].get_state(),
                {"is_on": False, "press_count": 0},
            )
        finally:
            invalid_app.extensions["bulb_database"].engine.dispose()

    def test_chat_rejects_missing_recaptcha(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "電球の消し方", "history": []},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "reCAPTCHA の確認を完了してください。"},
        )

    def test_toggle_rejects_recaptcha_action_mismatch(self):
        mismatched_app = create_app(
            {
                "TESTING": True,
                "DATABASE_URL": "sqlite:///:memory:",
                "RECAPTCHA_PROJECT_ID": "test-project",
                "RECAPTCHA_CLIENT": FakeRecaptchaClient(action="CHAT"),
            }
        )
        try:
            response = mismatched_app.test_client().post(
                "/api/toggle", json={"recaptcha_token": "chat-token"}
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(
                mismatched_app.extensions["bulb_database"].get_state(),
                {"is_on": False, "press_count": 0},
            )
        finally:
            mismatched_app.extensions["bulb_database"].engine.dispose()


if __name__ == "__main__":
    unittest.main()
