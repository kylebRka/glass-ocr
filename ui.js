"use strict";

const strings = {
  en: {
    title: "PDF to editable files", subtitle: "Recognize text and tables on your device with OCRia-nano-1.",
    drop: "Drop your PDF here", choose: "or click to choose a file", format: "Output format", range: "Pages",
    settings: "OCR settings", resolution: "Scan resolution · DPI", ocr: "Recognize scans",
    headers: "Keep headers and footers", auto: "OCRia automatically detects Russian and English by text line.",
    convert: "Convert PDF", privacy: "Local processing", working: "Recognizing and exporting…",
    done: "Conversion complete. Your file is ready.", pdf: "Choose one valid PDF.",
    size: "Choose a PDF of up to 125 MB.", options: "Check the page range (for example, 1-3, 5) and resolution.",
    empty: "No text found. For scanned PDFs, enable scan recognition.",
    tables: "No tables found. Try Word export to recover the text.", timeout: "Timed out. Try fewer pages or a lower DPI.",
    engine: "LiteParse is missing. Follow the installation steps in the README.",
    failed: "Conversion failed. Check the details below.",
    libreoffice: "Install LibreOffice to export .doc.",
    legacy: "The format converter did not produce a valid file.",
    mac: "Native .pages export requires Apple Pages on macOS.",
    pagesHint: "Requires Apple Pages. macOS may ask permission to control Pages.",
    xlsxHint: "Exports each detected table as a separate sheet.",
    busy: "A conversion is already in progress.", forbidden: "Reload Glass OCR and try again.",
    local: "The local service is unavailable. Launch Glass OCR again.",
  },
  ru: {
    title: "Из PDF в редактируемый файл", subtitle: "Распознавание текста и таблиц на твоём устройстве с OCRia-nano-1.",
    drop: "Перетащи сюда PDF", choose: "или нажми, чтобы выбрать файл", format: "Формат файла", range: "Страницы",
    settings: "Настройки распознавания", resolution: "Разрешение скана · DPI", ocr: "Распознавать сканы",
    headers: "Сохранять колонтитулы", auto: "OCRia автоматически определяет русский и английский по строкам.",
    convert: "Конвертировать PDF", privacy: "Локальная обработка", working: "Распознаю и сохраняю…",
    done: "Конвертация завершена. Файл готов.", pdf: "Выбери один корректный PDF.",
    size: "Выбери PDF размером до 125 МБ.", options: "Проверь диапазон (например, 1-3, 5) и разрешение.",
    empty: "Текст не найден. Если это скан, включи распознавание.",
    tables: "Таблицы не найдены. Попробуй формат Word для экспорта текста.",
    timeout: "Время вышло. Попробуй выбрать меньше страниц или снизить DPI.",
    engine: "Не найден LiteParse. Установи его по инструкции в README.",
    failed: "Конвертация не удалась. Подробности ниже.",
    libreoffice: "Для экспорта .doc установи LibreOffice.",
    legacy: "Конвертер формата не создал корректный файл.",
    mac: "Для экспорта .pages нужны macOS и Apple Pages.",
    pagesHint: "Нужен Apple Pages. macOS может запросить разрешение на управление Pages.",
    xlsxHint: "Для каждой найденной таблицы создаётся отдельный лист.",
    busy: "Конвертация уже выполняется.", forbidden: "Перезагрузи Glass OCR и попробуй ещё раз.",
    local: "Локальная служба недоступна. Запусти Glass OCR заново.",
  },
};

const byId = (id) => document.getElementById(id);
let lang = localStorage.getItem("glass-ocr-language") ||
  (navigator.language.toLowerCase().startsWith("ru") ? "ru" : "en");
if (!(lang in strings)) lang = "en";
let file = null;
let config = null;
let busy = false;
let statusKey = "";
const tr = (key) => strings[lang][key] || strings[lang].failed;
const format = byId("format");

function formatNote() {
  const hints = { doc: config?.doc ? "" : "libreoffice", pages: "pagesHint", xlsx: "xlsxHint" };
  const note = byId("format-note");
  const key = hints[format.value];
  note.hidden = !key;
  note.textContent = key ? tr(key) : "";
}

function language(next) {
  lang = next;
  localStorage.setItem("glass-ocr-language", lang);
  document.documentElement.lang = lang;
  byId("languages").setAttribute("aria-label", lang === "ru" ? "Язык интерфейса" : "Interface language");
  for (const code of ["en", "ru"]) byId(code).setAttribute("aria-pressed", code === lang);
  for (const item of document.querySelectorAll("[data-t]")) item.textContent = tr(item.dataset.t);
  if (file) byId("file-name").textContent = file.name;
  if (statusKey) byId("status").textContent = tr(statusKey);
  formatNote();
}

function status(key = "", details = "", error = false) {
  statusKey = key;
  byId("status").hidden = !key;
  byId("status").textContent = key ? tr(key) : "";
  byId("status").dataset.error = error;
  byId("detail").hidden = !details;
  byId("detail").textContent = details;
}

function selected(files) {
  if (busy || !files.length) return;
  const picked = files[0];
  const valid = files.length === 1 && /\.pdf$/i.test(picked.name);
  const sizeOK = picked.size <= 125 * 1024 * 1024;
  if (!valid || !sizeOK) {
    file = null;
    byId("file-name").textContent = tr("drop");
    byId("submit").disabled = true;
    status(valid ? "size" : "pdf", "", true);
    return;
  }
  file = picked;
  byId("file-name").textContent = file.name;
  byId("submit").disabled = !config;
  status();
}

for (const code of ["en", "ru"]) byId(code).addEventListener("click", () => language(code));
byId("drop").addEventListener("click", () => byId("pdf").click());
byId("pdf").addEventListener("change", (event) => {
  selected(event.target.files);
  event.target.value = "";
});
for (const eventName of ["dragover", "drop"]) document.addEventListener(eventName, (event) => {
  if (event.dataTransfer?.types.includes("Files")) event.preventDefault();
});
byId("drop").addEventListener("dragover", (event) => {
  event.preventDefault();
  if (!busy) byId("drop").classList.add("active");
});
byId("drop").addEventListener("dragleave", () => byId("drop").classList.remove("active"));
byId("drop").addEventListener("drop", (event) => {
  event.preventDefault();
  byId("drop").classList.remove("active");
  selected(event.dataTransfer.files);
});
format.addEventListener("change", formatNote);
language(lang);

async function initialize() {
  try {
    const response = await fetch("/config");
    if (!response.ok) throw new Error();
    config = await response.json();
    format.querySelector('[value="pages"]').hidden = !config.mac;
    format.querySelector('[value="pages"]').disabled = !config.mac;
    byId("submit").disabled = !file;
    formatNote();
  } catch {
    status("local", "", true);
  }
}

byId("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!file || !config || busy) return;
  const target = format.value;
  if (target === "doc" && !config.doc) {
    status("libreoffice", "", true);
    return;
  }
  busy = true;
  byId("submit").disabled = true;
  byId("drop").disabled = true;
  status("working");
  try {
    const response = await fetch("/convert", {
      method: "POST", body: file, headers: {
        "Content-Type": "application/pdf", "X-Glass-Token": config.token, "X-Format": target,
        "X-Dpi": byId("dpi").value, "X-Pages": byId("pages").value.replace(/[–—]/g, "-").replace(/\s+/g, ""),
        "X-Ocr": byId("ocr").checked ? "on" : "off", "X-Headers": byId("headers").checked ? "on" : "off",
      },
    });
    if (!response.ok) {
      const error = await response.json();
      status(error.key, error.detail, true);
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = file.name.replace(/\.pdf$/i, "") + "." + target;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    status("done");
  } catch {
    status("local", "", true);
  } finally {
    busy = false;
    byId("submit").disabled = false;
    byId("drop").disabled = false;
  }
});

initialize();
