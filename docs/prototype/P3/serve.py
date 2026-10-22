"""Static server for the prototype.

`python -m http.server` on Windows can serve .js as text/plain (it reads MIME types from the
registry), and browsers refuse ES modules with that type. This pins the types and disables
caching, nothing else. Usage: py serve.py [port]  (default 8419), then open http://localhost:<port>/
"""
import functools
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json",
         ".html": "text/html", ".svg": "image/svg+xml", ".ts": "text/plain", ".md": "text/markdown"}


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, **TYPES}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8419
    root = os.path.dirname(os.path.abspath(__file__))
    handler = functools.partial(Handler, directory=root)
    print(f"Serving {root} at http://localhost:{port}/")  # leftovers-allow: the server tells the user where to open it
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
