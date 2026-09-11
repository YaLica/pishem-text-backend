import os
from app import app

# WSGI entrypoint for hosting panels that ask for a Python module/object.
application = app

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
