# Static Frontend Separation

This repo now supports a static frontend bundle that can be hosted on GCS while the Flask app remains the API/backend layer.

## Intended layout

```text
frontend/
  entry.html
  index.html
  assets/
    styles.css
    recaptcha.js
    bulb.js
    chat.js
```

## Runtime behavior

Set `FRONTEND_DIST_DIR` to the directory containing the built static frontend pages. When that value is configured, the Flask app serves `entry.html` and `index.html` from that directory instead of the legacy `templates/` files.

This keeps the current app compatible with the existing template-based setup while making future GCS deployment straightforward.

## Example

```bash
export FRONTEND_DIST_DIR=./frontend
python app.py
```

The backend continues to provide the API endpoints for:

- `/api/site-entry`
- `/api/toggle`
- `/api/chat`

The frontend can then call those endpoints from a separate static host such as Google Cloud Storage.
