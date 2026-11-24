# Glass OCR

[Русский](README.ru.md)

A local PDF converter for macOS (Apple silicon) and Windows (x64/ARM64). Drop a scan or a PDF with selectable text into the browser window opened by the launcher. OCRia-nano-1 through LiteParse recognizes English and Russian automatically, line by line. The interface is available in English and Russian.

| Format | Output | Requirements |
|---|---|---|
| .docx | Editable text and tables | LiteParse |
| .xlsx | One sheet per detected table, with merged cells where detected | LiteParse |
| .doc | Native Word 97–2003 binary document | Built into macOS, LibreOffice on Windows |
| .pages | Native Apple Pages document | macOS with Apple Pages and Automation permission |

The app binds to the loopback address. PDFs are processed locally in a temporary directory and cleared after each job. The initial dependency and model downloads require internet. The app is distributed as source with launch scripts.

## Set up

Install [64-bit Python 3.11–3.14](https://www.python.org/downloads/). On macOS use native arm64 Python. Download or clone this repository and open a terminal in its folder. Read the [model license](https://huggingface.co/llamaindex/OCRia-nano-1/blob/v1.0.0/LICENSE) before running the model download command.

### macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m liteparse.cli models pull ocria-nano
sh start-mac.command
```

### Windows (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m liteparse.cli models pull ocria-nano
.\start-windows.bat
```

After setup, use the last command or double-click the launcher. Close its terminal to stop the app. For .doc export on Windows, install [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/) in the default location or add its executable to PATH. For .pages, install Apple Pages, then allow the requested Apple Events permission if macOS asks. You can also open the DOCX export directly in Pages and save it there.

## Use

Drop one PDF (up to 125 MiB), choose a destination format and click **Convert PDF**. To export specific pages, enter a range such as `1-3, 5`. In **OCR settings**, adjust the scan resolution, disable scan recognition for digital documents or retain running headers and footers.

Export reconstructs editable text and table structure. Complex page layouts, images, exact typography and embedded links may be omitted or simplified. Review OCR output before reuse, especially short numbers in scanned tables. Excel cells are stored as text so document content cannot become formulas and leading zeros are preserved. Convert cells to numbers in Excel if you need to calculate with them.

## Tests

Run `python -m unittest -v`. It checks Word and Excel package XML, merged cells, Cyrillic, literal spreadsheet values, settings forwarded to LiteParse and the loopback API. The workflow runs these checks on macOS and Windows without downloading model weights.

On an Apple M1 Pro, LiteParse 2.21.2 and OCRia-nano-1 1.0.0 were tested with two synthetic one-page, bilingual PDFs. The scanned page took about 0.29 s inside LiteParse at 250 DPI, recognized both languages and recovered the five-row table, with three incorrect or empty quantity cells. The text-layer PDF retained the quantities and surfaced several Cyrillic letter substitutions. A single clean scan is too small for comparative benchmarking.

## Model credit and license

OCRia-nano-1 by LlamaIndex, Inc. is used through [LiteParse](https://github.com/run-llama/liteparse). See the original [model card](https://huggingface.co/llamaindex/OCRia-nano-1) and [technical report](https://www.llamaindex.ai/ocria/ocria-nano-1-report.pdf). The upstream weights are downloaded separately and are used as provided. LiteParse installs a copy of the model license alongside them. Review its commercial and competing-service restrictions before using the model in a product or service.
