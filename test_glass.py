from http.client import HTTPConnection
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import errno
from threading import Thread
import unittest
import subprocess
import sys
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app import ConversionError, Handler, ThreadingHTTPServer, convert, export_legacy
from exports import SHEET, WORD, Table, docx, markdown_blocks, xlsx


MARKDOWN = r"""# Проверка & check

Символы < > & остаются текстом.
- Пример

| Имя | Значение |
|---|---|
| Кириллица | =1+2 |
| a\|b | 0009 |

<table>
<tr><th colspan="2" rowspan="2">Total &amp; VAT</th><th>Price</th></tr>
<tr><td>100<br>200</td></tr>
<tr><td>A</td><td>B</td><td>C</td></tr>
</table>
"""


def xml(data, member):
    with ZipFile(BytesIO(data)) as archive:
        assert archive.testzip() is None
        for entry in archive.namelist():
            ET.fromstring(archive.read(entry))
        return ET.fromstring(archive.read(member))


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.blocks = list(markdown_blocks(MARKDOWN))
        self.tables = [block for block in self.blocks if isinstance(block, Table)]

    def test_document_is_editable_with_merged_cells(self):
        root = xml(docx(self.blocks), "word/document.xml")
        ns = {"w": WORD}
        self.assertEqual(len(root.findall(".//w:tbl", ns)), 2)
        self.assertEqual(len(root.findall(".//w:vMerge", ns)), 2)
        self.assertEqual(len(root.findall(".//w:gridSpan", ns)), 2)
        self.assertIn("Проверка & check", "".join(root.itertext()))
        self.assertIn("a|b", "".join(root.itertext()))

    def test_workbook_has_separate_sheets_and_literal_data(self):
        data = xlsx(self.tables)
        ns = {"s": SHEET}
        workbook = xml(data, "xl/workbook.xml")
        self.assertEqual(len(workbook.findall(".//s:sheet", ns)), 2)
        first = xml(data, "xl/worksheets/sheet1.xml")
        self.assertIsNone(first.find(".//s:f", ns))
        self.assertIn("=1+2", "".join(first.itertext()))
        self.assertIn("0009", "".join(first.itertext()))
        second = xml(data, "xl/worksheets/sheet2.xml")
        self.assertEqual(second.find(".//s:mergeCell", ns).attrib["ref"], "A1:B2")
        self.assertEqual(second.find(".//s:c[@r='C2']/s:is/s:t", ns).text, "100\n200")

    @unittest.skipUnless(sys.platform == "darwin", "macOS textutil required")
    def test_native_word_97_export_on_macos(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            data = export_legacy(folder, docx(self.blocks), "doc")
            output = folder / "opened.doc"
            output.write_bytes(data)
            html = subprocess.check_output(["/usr/bin/textutil", "-convert", "html", "-stdout", output])
            self.assertIn("<table", html.decode("utf-8"))
            self.assertIn("Кириллица", html.decode("utf-8"))

    def test_conversion_flags_and_empty_tables(self):
        with TemporaryDirectory() as directory, patch("app.find_spec", return_value=True):
            source = Path(directory) / "input.pdf"
            def parse(args):
                self.assertIn("ocria-nano", args)
                self.assertIn("--no-ocr", args)
                self.assertIn("--keep-headers-footers", args)
                self.assertEqual(args[args.index("--target-pages") + 1], "2-3")
                source.with_suffix(".md").write_text("# Только текст", encoding="utf-8")
            with patch("app.command", side_effect=parse):
                with self.assertRaises(ConversionError) as raised:
                    convert(source, "xlsx", 300, "2-3", False, True)
            self.assertEqual(raised.exception.key, "tables")


class WebTests(unittest.TestCase):
    def test_local_api_round_trip_and_validation(self):
        try:
            listener = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except PermissionError as error:
            if error.errno in (errno.EPERM, errno.EACCES):
                self.skipTest("Loopback bind is restricted in this environment")
            raise
        with listener as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                def request(verb, path, body=None, headers=None):
                    connection.request(verb, path, body, headers or {})
                    response = connection.getresponse()
                    return response.status, response.read()

                status, body = request("GET", "/")
                self.assertEqual(status, 200)
                self.assertIn(b"Glass OCR", body)
                status, body = request("GET", "/config")
                self.assertEqual(status, 200)
                headers = {"X-Glass-Token": json.loads(body)["token"], "X-Format": "docx"}
                self.assertEqual(request("POST", "/convert", b"%PDF-1.7")[0], 403)
                self.assertEqual(request("POST", "/convert", b"fake", headers)[0], 415)
                self.assertEqual(request("POST", "/convert", b"%PDF-1.7", {**headers, "X-Pages": "bad"})[0], 400)
                with patch("app.convert", return_value=docx([(0, "Русский")])) as mock:
                    status, body = request("POST", "/convert", b"%PDF-1.7", headers)
                    self.assertEqual(status, 200)
                    self.assertIn("Русский", "".join(xml(body, "word/document.xml").itertext()))
                    self.assertFalse(mock.call_args.args[0].exists())
            finally:
                connection.close()
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    unittest.main()
