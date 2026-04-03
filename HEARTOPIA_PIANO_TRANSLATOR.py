import re
import tkinter as tk
import webbrowser
from html.parser import HTMLParser
from tkinter import messagebox
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# CSS class used by Heartopia for one visible row of notes.
ROW_CLASS = "flex flex-wrap justify-center items-center w-full gap-x-2 gap-y-1 px-1"

# CSS class used by Heartopia for blank spacing between rows.
SPACER_CLASS = "h-[0.8em] w-full"

# Official Heartopia music browser page shown as a shortcut in the launcher.
OFFICIAL_MUSIC_URL = "https://www.heartopia-hub.com/es/music"

# All user-facing text for the launcher and dialogs.
# The app switches between these dictionaries when the language button is pressed.
UI_TEXT = {
    "en": {
        "window_title": "Heartopia Piano Translator",
        "title": "Heartopia Piano Translator",
        "subtitle": "Paste a Heartopia music page URL.",
        "translate_button": "Translate + Show",
        "language_button": "Spanish",
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

# Maps each parsed Heartopia note symbol to the keyboard key that should be played.
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

# Known exception types and the localized dialog keys they should use.
ERROR_TEXT_BY_EXCEPTION = {
    HTTPError: ("download_error_title", "download_error_message"),
    URLError: ("url_error_title", "url_error_message"),
    OSError: ("file_error_title", "file_error_message"),
}


def classify_tex(tex: str) -> tuple[str, str]:
    """Convert a Heartopia TeX note annotation into the app's note symbol."""
    tex = tex.strip()

    # Note modifiers are encoded as TeX fragments inside the annotation.
    double_dot = "\\ddot{" in tex
    single_dot = "\\dot{" in tex
    sharp = "^\\sharp" in tex

    # Pull the numbered scale degree out of markup like \textsf{5}.
    number_match = re.search(r"textsf\{(\d)\}", tex)
    if not number_match:
        return tex, "unknown"

    number = number_match.group(1)
    symbol = number
    category = "plain"

    # Dots change octave/variant and become part of the symbol key we translate later.
    if double_dot:
        symbol += ".."
        category = "double_dotted"
    elif single_dot:
        symbol += "."
        category = "dotted"

    # Sharps are appended as a final marker.
    if sharp:
        symbol += "#"
        category = f"{category}_sharp"

    return symbol, category


class NoteHTMLParser(HTMLParser):
    """Parse Heartopia music HTML into rows of note symbols."""

    def __init__(self) -> None:
        super().__init__()
        # Each item is either:
        # - a list of note tokens for one row
        # - None for an intentionally blank spacer row
        self.rows: list[list[str] | None] = []

        # While parsing, the current visible row is accumulated here.
        self.current_row: list[str] | None = None

        # Tracks nested div depth so we know when a row container ends.
        self.row_depth = 0

        # These fields capture the raw contents of <annotation> tags.
        self.capture_annotation = False
        self.annotation_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Start collecting rows, spacers, or TeX annotations when seen in the HTML."""
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")

        # A new note row starts here.
        if tag == "div" and class_name == ROW_CLASS:
            self.current_row = []
            self.row_depth = 1
            return

        # Nested divs inside the row count toward the row container depth.
        if self.current_row is not None and tag == "div":
            self.row_depth += 1

        # Spacer rows become blank lines in the translated output.
        if tag == "div" and class_name == SPACER_CLASS:
            self.rows.append(None)

        # The actual note markup is stored inside TeX annotations.
        if tag == "annotation" and attrs_dict.get("encoding") == "application/x-tex":
            self.capture_annotation = True
            self.annotation_parts = []

    def handle_endtag(self, tag: str) -> None:
        """Finish annotations and close a row when its wrapper div ends."""
        if tag == "annotation" and self.capture_annotation:
            tex = "".join(self.annotation_parts)
            symbol, _category = classify_tex(tex)

            # If a note appears outside a known row wrapper, preserve it anyway.
            if self.current_row is None:
                self.rows.append([symbol])
            else:
                self.current_row.append(symbol)

            self.capture_annotation = False
            self.annotation_parts = []
            return

        # When the outer row div closes, store the completed row.
        if self.current_row is not None and tag == "div":
            self.row_depth -= 1
            if self.row_depth == 0:
                self.rows.append(self.current_row)
                self.current_row = None

    def handle_data(self, data: str) -> None:
        """Capture raw annotation text and visible bar separators."""
        if self.capture_annotation:
            self.annotation_parts.append(data)
            return

        # Preserve "|" markers that appear inside note rows.
        if self.current_row is not None and data.strip() == "|":
            self.current_row.append("|")


class PageTitleParser(HTMLParser):
    """Extract a useful page title from title, meta, and h1 elements."""

    def __init__(self) -> None:
        super().__init__()
        self.capture_title = False
        self.title_parts: list[str] = []
        self.capture_h1 = False
        self.h1_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track whether we are inside a title/h1 and read og:title when present."""
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
        """Stop capturing text when title or h1 tags close."""
        if tag == "title":
            self.capture_title = False
        if tag == "h1":
            self.capture_h1 = False

    def handle_data(self, data: str) -> None:
        """Store title and heading text as the parser encounters it."""
        if self.capture_title:
            self.title_parts.append(data)
        if self.capture_h1:
            self.h1_parts.append(data)


def extract_page_title(html: str) -> str:
    """Choose the best title available from the page HTML."""
    parser = PageTitleParser()
    parser.feed(html)

    # Prefer the visible heading first, then fall back to document title/meta title.
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
    """Parse Heartopia rows, with a regex fallback for simpler HTML layouts."""
    parser = NoteHTMLParser()
    parser.feed(html)

    if parser.rows:
        return parser.rows

    # Fallback: if row wrappers are missing, still extract all TeX annotations in order.
    annotations = re.findall(
        r'<annotation encoding="application/x-tex">(.*?)</annotation>',
        html,
        re.DOTALL,
    )
    if not annotations:
        return []

    return [[classify_tex(tex)[0] for tex in annotations]]


def translate_symbol(symbol: str) -> str:
    """Translate one parsed symbol to the target keyboard key."""
    return TRANSLATION_MAP.get(symbol, symbol)


def translated_sequence(html: str) -> str:
    """Convert extracted rows into the multiline output shown in the app."""
    lines: list[str] = []

    for row in extract_rows(html):
        if row is None:
            # Spacer rows become blank lines in the output.
            lines.append("")
            continue
        lines.append(" ".join(translate_symbol(symbol) for symbol in row))

    return "\n".join(lines)


def fetch_html(url: str) -> str:
    """Download the source page using a browser-like user agent."""
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
    """Validate the input and return the downloaded HTML."""
    if not source:
        raise ValueError("missing_url")

    return fetch_html(source)


def translate_file(source: str | None = None) -> tuple[str, str]:
    """Fetch a song page and return its cleaned title plus translated notes."""
    html = read_source(source)
    title = extract_page_title(html)
    result = translated_sequence(html)
    return title, result


def show_overlay(title_text: str, text: str) -> None:
    """Show the translated notes in a separate always-on-top window."""
    root = tk.Tk()
    root.title(title_text)
    root.geometry("980x520+80+60")
    root.attributes("-topmost", True)
    root.configure(bg="#101418")

    # Main container for the translation preview window.
    container = tk.Frame(root, bg="#101418", padx=18, pady=18)
    container.pack(fill="both", expand=True)

    # Song title at the top.
    header = tk.Label(
        container,
        text=title_text,
        fg="#f4f7fb",
        bg="#101418",
        font=("Consolas", 18, "bold"),
        anchor="w",
    )
    header.pack(fill="x")

    # Read-only text box that displays the translated piano sequence.
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

    # Escape closes just the overlay, not the launcher.
    root.bind("<Escape>", lambda _event: root.destroy())
    root.mainloop()


def run_gui() -> None:
    """Build and run the launcher window."""
    # The launcher starts in English and can be toggled to Spanish.
    current_language = "en"

    def tr(key: str) -> str:
        """Look up the localized UI text for the current language."""
        return UI_TEXT[current_language][key]

    # Main application launcher window.
    launcher = tk.Tk()

    def show_error(title_key: str, message_key: str, **kwargs: object) -> None:
        """Show a localized error dialog."""
        messagebox.showerror(
            tr(title_key),
            tr(message_key).format(**kwargs),
            parent=launcher,
        )

    def apply_language() -> None:
        """Refresh all launcher labels/buttons after a language change."""
        launcher.title(tr("window_title"))
        title.config(text=tr("title"))
        subtitle.config(text=tr("subtitle"))
        run_button.config(text=tr("translate_button"))
        language_button.config(text=tr("language_button"))
        help_text.config(text=tr("help_text"))

    def translate_and_show() -> None:
        """Translate the pasted URL and open the result overlay."""
        source = source_var.get().strip()
        try:
            title_text, translated_text = translate_file(source)
            show_overlay(title_text, translated_text)
        except ValueError as exc:
            if str(exc) == "missing_url":
                show_error("missing_url_title", "missing_url_message")
            else:
                show_error("unexpected_error_title", "unexpected_error_message", error=exc)
        except tuple(ERROR_TEXT_BY_EXCEPTION) as exc:
            # Map the specific exception type to its matching localized dialog strings.
            title_key, message_key = ERROR_TEXT_BY_EXCEPTION[type(exc)]
            show_error(
                title_key,
                message_key,
                code=getattr(exc, "code", ""),
                url=getattr(exc, "url", ""),
                reason=getattr(exc, "reason", ""),
                error=exc,
            )
        except Exception as exc:
            show_error("unexpected_error_title", "unexpected_error_message", error=exc)

    def toggle_language() -> None:
        """Switch the launcher UI between English and Spanish."""
        nonlocal current_language
        current_language = "es" if current_language == "en" else "en"
        apply_language()

    # Configure the launcher window.
    launcher.title(tr("window_title"))
    launcher.geometry("760x230+120+90")
    launcher.configure(bg="#101418")

    # Outer layout container.
    container = tk.Frame(launcher, bg="#101418", padx=18, pady=18)
    container.pack(fill="both", expand=True)

    # Main launcher heading.
    title = tk.Label(
        container,
        text=tr("title"),
        fg="#f4f7fb",
        bg="#101418",
        font=("Consolas", 18, "bold"),
        anchor="w",
    )
    title.pack(fill="x")

    # Short instruction under the title.
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

    # Clickable shortcut to browse official music pages before pasting a song URL.
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
    official_link.bind("<Button-1>", lambda _event: webbrowser.open_new_tab(OFFICIAL_MUSIC_URL))

    # Input field for the Heartopia song URL.
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

    # Row for the main action button and language toggle.
    button_row = tk.Frame(container, bg="#101418")
    button_row.pack(fill="x")

    # Main translation action.
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

    # Language toggle button.
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

    # Small usage hint at the bottom of the launcher.
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

    # Make sure the initial language state is applied and put the cursor in the URL box.
    apply_language()
    entry.focus_set()
    launcher.mainloop()


def main() -> None:
    """Application entry point."""
    run_gui()


if __name__ == "__main__":
    main()
