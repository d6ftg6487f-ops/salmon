"""Serve the real app against a disposable SQLite database for browser tests."""

import os
import signal
import sys
import tempfile
from pathlib import Path


def main():
    # The override lets the same suite verify an untouched baseline checkout.
    root = Path(os.environ.get("FRONTEND_APP_ROOT", Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(root.resolve()))
    for name in ("K_SERVICE", "CLOUD_SQL_CONNECTION_NAME", "GOOGLE_CLOUD_PROJECT"):
        os.environ.pop(name, None)

    with tempfile.TemporaryDirectory(prefix="salmon-frontend-") as directory:
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(directory, 'bulb.db')}"
        from app import app

        def stop(_signum, _frame):
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, stop)
        try:
            app.run(host="127.0.0.1", port=8765, use_reloader=False)
        finally:
            app.extensions["bulb_database"].engine.dispose()


if __name__ == "__main__":
    main()
