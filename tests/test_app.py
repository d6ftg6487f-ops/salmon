import tempfile
import unittest
from pathlib import Path

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
        self.assertIn("消えています".encode(), response.data)
        self.assertIn(
            "押した回数 <span id=\"count\">0</span> 回".encode(),
            response.data,
        )

    def test_toggle_updates_and_persists_state_and_count(self):
        first_response = self.client.post("/api/toggle")
        second_response = self.client.post("/api/toggle")

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
            first_app.test_client().post("/api/toggle")
            first_app.extensions["bulb_database"].engine.dispose()

            second_app = create_app({"DATABASE_URL": database_url})
            response = second_app.test_client().get("/")

            self.assertIn(
                "押した回数 <span id=\"count\">1</span> 回".encode(),
                response.data,
            )
            self.assertIn("ついています".encode(), response.data)
            second_app.extensions["bulb_database"].engine.dispose()


if __name__ == "__main__":
    unittest.main()
