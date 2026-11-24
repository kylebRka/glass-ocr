"""Local-only PDF conversion server and desktop launcher."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import find_spec
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Lock
from urllib.parse import unquote
import webbrowser
from zipfile import is_zipfile, ZipFile

from exports import Table, docx, markdown_blocks, xlsx


ROOT = Path(__file__).resolve().parent
MAX_BYTES = 125 * 1024 * 1024
TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "pages": "application/vnd.apple.pages",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8"),
          "/ui.js": ("ui.js", "text/javascript; charset=utf-8")}
TOKEN = secrets.token_urlsafe()
BUSY = Lock()


class ConversionError(Exception):
    def __init__(self, key, detail="", http_status=422):
        self.key, self.detail, self.http_status = key, detail, http_status


def libreoffice():
    candidates = [
        shutil.which("soffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        *(str(Path(os.environ.get(key, "C:/Program Files")) / "LibreOffice/program/soffice.exe")
          for key in ("ProgramFiles", "ProgramFiles(x86)")),
    ]
    return next((exe for exe in candidates if exe and Path(exe).is_file()), None)


def command(args, timeout=900):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise ConversionError("timeout") from error
    except FileNotFoundError as error:
        raise ConversionError("engine") from error
    if result.returncode:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise ConversionError("failed", detail[-2500:])


PAGES_SCRIPT = """
on run argv
    set sourceFile to POSIX file (item 1 of argv)
    set destinationFile to POSIX file (item 2 of argv)
    tell application id "com.apple.Pages"
        set importedDocument to open sourceFile
        try
            save importedDocument in destinationFile
        on error errorMessage number errorNumber
            close importedDocument saving no
            error errorMessage number errorNumber
        end try
        close importedDocument saving no
    end tell
end run
"""


def export_legacy(work, data, target):
    source = work / "result.docx"
    source.write_bytes(data)
    result = source.with_suffix("." + target)
    if target == "doc":
        writer = libreoffice()
        if not writer:
            raise ConversionError("libreoffice")
        command([writer, f"-env:UserInstallation={(work / 'lo-profile').as_uri()}", "--headless",
                 "--convert-to", "doc:MS Word 97", "--outdir", str(work), str(source)], timeout=120)
        data = result.read_bytes() if result.is_file() else b""
        if not data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise ConversionError("legacy")
        return data
    if sys.platform != "darwin":
        raise ConversionError("mac")
    command(["/usr/bin/osascript", "-e", PAGES_SCRIPT, str(source), str(result)], timeout=120)
    if not is_zipfile(result):
        raise ConversionError("legacy")
    with ZipFile(result) as archive:
        if not any(name.startswith("Index/") for name in archive.namelist()):
            raise ConversionError("legacy")
    return result.read_bytes()


def convert(source, target, dpi=250, pages="", ocr=True, headers=False):
    if find_spec("liteparse") is None:
        raise ConversionError("engine")
    output = source.with_suffix(".md")
    args = [sys.executable, "-m", "liteparse.cli", "parse", str(source),
            "--output", str(output), "--format", "markdown", "--ocr-backend", "ocria-nano",
            "--image-mode", "off", "--no-links", "--dpi", str(dpi), "--max-pages", "1000000"]
    if pages:
        args += ["--target-pages", pages]
    if not ocr:
        args.append("--no-ocr")
    if headers:
        args.append("--keep-headers-footers")
    command(args)
    if not output.is_file():
        raise ConversionError("failed", "LiteParse did not produce Markdown.")
    blocks = list(markdown_blocks(output.read_text(encoding="utf-8")))
    if not blocks:
        raise ConversionError("empty")
    if target == "xlsx":
        tables = [block for block in blocks if isinstance(block, Table)]
        if not tables:
            raise ConversionError("tables")
        return xlsx(tables)
    data = docx(blocks)
    return data if target == "docx" else export_legacy(source.parent, data, target)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(60)

    def allowed(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def reply(self, status, mime, data, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, key, detail=""):
        self.reply(status, "application/json", json.dumps({"key": key, "detail": detail}).encode())

    def do_GET(self):
        if not self.allowed():
            return self.error(403, "forbidden")
        if self.path == "/config":
            data = {"token": TOKEN, "mac": sys.platform == "darwin", "doc": bool(libreoffice())}
            return self.reply(200, "application/json", json.dumps(data).encode())
        if self.path not in ASSETS:
            return self.error(404, "failed")
        filename, mime = ASSETS[self.path]
        self.reply(200, mime, (ROOT / filename).read_bytes())

    def do_POST(self):
        if not self.allowed() or self.headers.get("X-Glass-Token") != TOKEN:
            return self.error(403, "forbidden")
        if self.path != "/convert":
            return self.error(404, "failed")
        target = self.headers.get("X-Format")
        pages = self.headers.get("X-Pages", "")
        try:
            size = int(self.headers.get("Content-Length", "0"))
            dpi = int(self.headers.get("X-Dpi", "250"))
        except ValueError:
            return self.error(400, "options")
        if not 0 < size <= MAX_BYTES:
            return self.error(413, "size")
        if target not in TYPES or not 150 <= dpi <= 400 or (pages and not re.fullmatch(
            r"[1-9][0-9]{0,5}(?:-[1-9][0-9]{0,5})?(?:,[1-9][0-9]{0,5}(?:-[1-9][0-9]{0,5})?)*", pages
        )):
            return self.error(400, "options")
        if target == "pages" and sys.platform != "darwin":
            return self.error(422, "mac")
        if target == "doc" and not libreoffice():
            return self.error(422, "libreoffice")
        if not BUSY.acquire(blocking=False):
            return self.error(409, "busy")
        try:
            with TemporaryDirectory(prefix="glass-ocr-") as directory:
                source = Path(directory) / "input.pdf"
                first = self.rfile.read(min(1024, size))
                if b"%PDF-" not in first:
                    return self.error(415, "pdf")
                with source.open("wb") as file:
                    file.write(first)
                    remaining = size - len(first)
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, 1024 * 1024))
                        if not chunk:
                            return self.error(400, "pdf")
                        file.write(chunk)
                        remaining -= len(chunk)
                data = convert(source, target, dpi, pages, self.headers.get("X-Ocr") != "off",
                               self.headers.get("X-Headers") == "on")
            self.reply(200, TYPES[target], data,
                       [("Content-Disposition", f'attachment; filename="converted.{target}"')])
        except ConversionError as error:
            self.error(error.http_status, error.key, error.detail)
        except TimeoutError:
            self.error(408, "timeout")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, OSError) as error:
            self.error(422, "failed", str(error))
        finally:
            BUSY.release()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--port", type=int, default=0)
    cli.add_argument("--no-browser", action="store_true")
    args = cli.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Glass OCR · {url}\nCtrl+C to close / для выхода", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
