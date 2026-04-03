import re
import tkinter as tk
import webbrowser
from tkinter import messagebox
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROW_CLASS = "flex flex-wrap justify-center items-center w-full gap-x-2 gap-y-1 px-1"
SPACER_CLASS = "h-[0.8em] w-full"
OFFICIAL_MUSIC_URL = "https://www.heartopia-hub.com/es/music"

UI_TEXT = {
    "en": {
        "window_title": "Heartopia Piano Translator",
        "title": "Heartopia Piano Translator",
        "subtitle": "Paste a Heartopia music page URL.",
        "translate_button": "Translate + Show",
        "language_button": "Español",
        "help_text": "Esc closes the template window after it opens.",
        "missing_url_title": "Missing URL",
        "missing_url_message": "Please enter a Heartopia music page URL.",
        "download_error_title": "Download Error",
        "download_error_message": "Failed to download the page:\nHTTP {code}\n{url}",
        "url_error_title": "URL Error",
        "url_error_message": "Failed to reach the URL:\n{reason}",
        "file_error_title": "File Error",
        "file_error_message": "File or window error:\n{error}",
        "unexpected_error_title": "Unexpected Error",
        "unexpected_error_message": "Unexpected error:\n{error}",
    },
    "es": {
        "window_title": "Traductor de Piano Heartopia",
        "title": "Traductor de Piano Heartopia",
        "subtitle": "Pega la URL de una pagina musical de Heartopia.",
        "translate_button": "Traducir + Mostrar",
        "language_button": "English",
        "help_text": "Esc cierra la ventana de la plantilla despues de abrirse.",
        "missing_url_title": "Falta la URL",
        "missing_url_message": "Introduce la URL de una pagina musical de Heartopia.",
        "download_error_title": "Error de Descarga",
        "download_error_message": "No se pudo descargar la pagina:\nHTTP {code}\n{url}",
        "url_error_title": "Error de URL",
        "url_error_message": "No se pudo acceder a la URL:\n{reason}",
        "file_error_title": "Error de Archivo",
        "file_error_message": "Error de archivo o ventana:\n{error}",
        "unexpected_error_title": "Error Inesperado",
        "unexpected_error_message": "Error inesperado:\n{error}",
    },
}

TRANSLATION_MAP = {
    "1": "z",
    "1.": "Q",
    "1.#": "2",
    "1..": "I",
    ".1": ",",
    ".1#": "L",
    "2": "X",
    "2.": "W",
    "2.#": "3",
    ".2": ".",
    ".2#": ";",
    "3": "C",
    "3.": "E",
    ".3": "/",
    "4": "V",
    "4.": "R",
    "4.#": "5",
    ".4": "O",
    ".4#": "0",
    "5": "B",
    "5#": "H",
    "5.": "T",
    "5.#": "6",
    ".5": "P",
    ".5#": "-",
    "6": "N",
    "6.": "Y",
    "6.#": "7",
    ".6": "[",
    ".6#": "=",
    "7": "M",
    "7.": "U",
    "7.#": "8",
    ".7": "]",
}


def classify_tex(tex: str) -> tuple[str, str]:
    tex = tex.strip()

    double_dot = "\\ddot{" in tex
    single_dot = "\\dot{" in tex
    sharp = "^\\sharp" in tex

    number_match = re.search(r"textsf\{(\d)\}", tex)
    if not number_match:
        return tex, "unknown"

    number = number_match.group(1)
    symbol = number
    category = "plain"

    if double_dot:
        symbol += ".."
        category = "double_dotted"
    elif single_dot:
        symbol += "."
        category = "dotted"

    if sharp:
        symbol += "#"
        category = f"{category}_sharp"

    return symbol, category


class NoteHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str] | None] = []
        self.current_row: list[str] | None = None
        self.row_depth = 0
        self.capture_annotation = False
        self.annotation_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")

        if tag == "div" and class_name == ROW_CLASS:
            self.current_row = []
            self.row_depth = 1
            return

        if self.current_row is not None and tag == "div":
            self.row_depth += 1

        if tag == "div" and class_name == SPACER_CLASS:
            self.rows.append(None)

        if tag == "annotation" and attrs_dict.get("encoding") == "application/x-tex":
            self.capture_annotation = True
            self.annotation_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "annotation" and self.capture_annotation:
            tex = "".join(self.annotation_parts)
            symbol, _category = classify_tex(tex)
            if self.current_row is None:
                self.rows.append([symbol])
            else:
                self.current_row.append(symbol)
            self.capture_annotation = False
            self.annotation_parts = []
            return

        if self.current_row is not None and tag == "div":
            self.row_depth -= 1
            if self.row_depth == 0:
                self.rows.append(self.current_row)
                self.current_row = None

    def handle_data(self, data: str) -> None:
        if self.capture_annotation:
            self.annotation_parts.append(data)
            return

        if self.current_row is not None and data.strip() == "|":
            self.current_row.append("|")


class PageTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture_title = False
        self.title_parts: list[str] = []
        self.capture_h1 = False
        self.h1_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "title":
            self.capture_title = True
        if tag == "meta" and attrs_dict.get("property") == "og:title":
            content = attrs_dict.get("content")
            if content:
                self.title_parts = [content]
        if tag == "h1":
            self.capture_h1 = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.capture_title = False
        if tag == "h1":
            self.capture_h1 = False

    def handle_data(self, data: str) -> None:
        if self.capture_title:
            self.title_parts.append(data)
        if self.capture_h1:
            self.h1_parts.append(data)


def extract_page_title(html: str) -> str:
    parser = PageTitleParser()
    parser.feed(html)

    for raw in (
        "".join(parser.h1_parts).strip(),
        "".join(parser.title_parts).strip(),
    ):
        if raw:
            cleaned = re.sub(r"\s+", " ", raw).strip()
            if " | " in cleaned:
                cleaned = cleaned.split(" | ", 1)[0].strip()
            return cleaned

    return "Translated Piano Template"


def extract_rows(html: str) -> list[list[str] | None]:
    parser = NoteHTMLParser()
    parser.feed(html)

    if parser.rows:
        return parser.rows

    annotations = re.findall(
        r'<annotation encoding="application/x-tex">(.*?)</annotation>',
        html,
        re.DOTALL,
    )
    if not annotations:
        return []

    return [[classify_tex(tex)[0] for tex in annotations]]


def translate_symbol(symbol: str) -> str:
    return TRANSLATION_MAP.get(symbol, symbol)


def translated_sequence(html: str) -> str:
    lines: list[str] = []

    for row in extract_rows(html):
        if row is None:
            lines.append("")
            continue
        lines.append(" ".join(translate_symbol(symbol) for symbol in row))

    return "\n".join(lines)


def fetch_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(request) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def read_source(source: str | None) -> str:
    if not source:
        raise ValueError("missing_url")

    return fetch_html(source)


def translate_file(source: str | None = None) -> tuple[str, str]:
    html = read_source(source)
    title = extract_page_title(html)
    result = translated_sequence(html)
    return title, result


def show_overlay(title_text: str, text: str) -> None:
    root = tk.Tk()
    root.title(title_text)
    root.geometry("980x520+80+60")
    root.attributes("-topmost", True)
    root.configure(bg="#101418")

    container = tk.Frame(root, bg="#101418", padx=18, pady=18)
    container.pack(fill="both", expand=True)

    header = tk.Label(
        container,
        text=title_text,
        fg="#f4f7fb",
        bg="#101418",
        font=("Consolas", 18, "bold"),
        anchor="w",
    )
    header.pack(fill="x")

    body = tk.Text(
        container,
        bg="#101418",
        fg="#d7e0ea",
        insertbackground="#d7e0ea",
        font=("Consolas", 22),
        wrap="none",
        relief="flat",
        padx=8,
        pady=8,
    )
    body.pack(fill="both", expand=True, pady=(12, 0))
    body.insert("1.0", text)
    body.config(state="disabled")

    root.bind("<Escape>", lambda _event: root.destroy())
    root.mainloop()


def run_gui() -> None:
    current_language = "en"

    def tr(key: str) -> str:
        return UI_TEXT[current_language][key]

    launcher = tk.Tk()
    launcher.title(tr("window_title"))
    launcher.geometry("760x230+120+90")
    launcher.configure(bg="#101418")

    container = tk.Frame(launcher, bg="#101418", padx=18, pady=18)
    container.pack(fill="both", expand=True)

    title = tk.Label(
        container,
        text=tr("title"),
        fg="#f4f7fb",
        bg="#101418",
        font=("Consolas", 18, "bold"),
        anchor="w",
    )
    title.pack(fill="x")

    subtitle = tk.Label(
        container,
        text=tr("subtitle"),
        fg="#9fb3c8",
        bg="#101418",
        font=("Consolas", 11),
        anchor="w",
        pady=8,
    )
    subtitle.pack(fill="x")

    official_link = tk.Label(
        container,
        text=OFFICIAL_MUSIC_URL,
        fg="#79b8ff",
        bg="#101418",
        font=("Consolas", 10, "underline"),
        anchor="w",
        cursor="hand2",
        pady=4,
    )
    official_link.pack(fill="x")
    official_link.bind(
        "<Button-1>",
        lambda _event: webbrowser.open_new_tab(OFFICIAL_MUSIC_URL),
    )

    source_var = tk.StringVar(value="")
    entry = tk.Entry(
        container,
        textvariable=source_var,
        font=("Consolas", 12),
        bg="#1a2128",
        fg="#e7edf3",
        insertbackground="#e7edf3",
        relief="flat",
    )
    entry.pack(fill="x", pady=(6, 10), ipady=8)

    button_row = tk.Frame(container, bg="#101418")
    button_row.pack(fill="x")

    def apply_language() -> None:
        launcher.title(tr("window_title"))
        title.config(text=tr("title"))
        subtitle.config(text=tr("subtitle"))
        run_button.config(text=tr("translate_button"))
        language_button.config(text=tr("language_button"))
        help_text.config(text=tr("help_text"))

    def translate_and_show() -> None:
        source = source_var.get().strip()
        try:
            title_text, translated_text = translate_file(source)
            show_overlay(title_text, translated_text)
        except ValueError as exc:
            if str(exc) == "missing_url":
                messagebox.showerror(
                    tr("missing_url_title"),
                    tr("missing_url_message"),
                    parent=launcher,
                )
            else:
                messagebox.showerror(
                    tr("unexpected_error_title"),
                    tr("unexpected_error_message").format(error=exc),
                    parent=launcher,
                )
        except HTTPError as exc:
            messagebox.showerror(
                tr("download_error_title"),
                tr("download_error_message").format(code=exc.code, url=exc.url),
                parent=launcher,
            )
        except URLError as exc:
            messagebox.showerror(
                tr("url_error_title"),
                tr("url_error_message").format(reason=exc.reason),
                parent=launcher,
            )
        except OSError as exc:
            messagebox.showerror(
                tr("file_error_title"),
                tr("file_error_message").format(error=exc),
                parent=launcher,
            )
        except Exception as exc:
            messagebox.showerror(
                tr("unexpected_error_title"),
                tr("unexpected_error_message").format(error=exc),
                parent=launcher,
            )

    def toggle_language() -> None:
        nonlocal current_language
        current_language = "es" if current_language == "en" else "en"
        apply_language()

    run_button = tk.Button(
        button_row,
        text=tr("translate_button"),
        command=translate_and_show,
        font=("Consolas", 11, "bold"),
        bg="#3a7a57",
        fg="#f4f7fb",
        relief="flat",
        padx=14,
        pady=8,
    )
    run_button.pack(side="right")

    language_button = tk.Button(
        button_row,
        text=tr("language_button"),
        command=toggle_language,
        font=("Consolas", 11, "bold"),
        bg="#2d4f73",
        fg="#f4f7fb",
        relief="flat",
        padx=14,
        pady=8,
    )
    language_button.pack(side="left")

    help_text = tk.Label(
        container,
        text=tr("help_text"),
        fg="#7f93a8",
        bg="#101418",
        font=("Consolas", 10),
        anchor="w",
        pady=14,
    )
    help_text.pack(fill="x")

    apply_language()
    entry.focus_set()
    launcher.mainloop()


def main() -> None:
    run_gui()


if __name__ == "__main__":
    main()
