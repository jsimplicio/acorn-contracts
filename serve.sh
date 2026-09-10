#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT=${PORT:-8791}
echo "Serving at http://localhost:$PORT/"
python3 - "$PORT" <<'EOF'
import sys, os, http.server

class SpaHandler(http.server.SimpleHTTPRequestHandler):
    """Real path-based routing (/button, /docs/token-api, ...) needs the
    server to fall back to index.html for any path that isn't a real file
    on disk, letting index.html's own client-side router read
    location.pathname and pick the right view. Without this, a hard
    refresh or a pasted link to /button 404s, since nothing on disk is
    literally named "button" -- only a real file like component-api/
    button.json is, and those keep being served normally, unaffected."""

    def do_GET(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        fs_path = self.translate_path(path)
        if not os.path.isfile(fs_path):
            self.path = "/index.html"
        return super().do_GET()

    def end_headers(self):
        # This wiki reads its own real data live via fetch() on every
        # navigation. A browser's default HTTP cache doesn't know a JSON
        # file just changed on disk and will happily serve a stale
        # response, which reads as "my fix isn't showing up" when it's
        # actually just a cached fetch from before the edit.
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
server = http.server.HTTPServer(("", port), SpaHandler)
server.serve_forever()
EOF
