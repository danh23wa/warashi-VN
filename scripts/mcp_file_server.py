"""MCP tools for finding and opening files in the user's Downloads folder."""

import os
import platform
import shutil
import subprocess
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP


FILES_ROOT = Path(
    os.environ.get("WARASHI_FILES_ROOT", Path.home() / "Downloads")
).expanduser().resolve()
IGNORED_DIRECTORIES = {".git", ".venv", "__pycache__", "cache", "node_modules"}

mcp = FastMCP("warashi-files")


def _safe_path(path: str) -> Path:
    """Resolve a user path and reject paths outside Downloads."""
    candidate = (FILES_ROOT / path).resolve()
    try:
        candidate.relative_to(FILES_ROOT)
    except ValueError as error:
        raise ValueError("The requested path is outside the Downloads folder.") from error
    return candidate


def _is_ignored(path: Path) -> bool:
    """Return whether a path is inside a directory that should be skipped."""
    return any(part in IGNORED_DIRECTORIES for part in path.parts) or path.name.startswith(
        "~$"
    )


def _fold_text(text: str) -> str:
    """Normalize case and Vietnamese diacritics for filename matching."""
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text.casefold())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")


def _clean_query(query: str) -> str:
    """Remove conversational politeness from a filename query."""
    folded = _fold_text(query)
    for phrase in ("cho ta", "cho toi", "giup ta", "giup toi"):
        folded = folded.replace(phrase, " ")
    return " ".join(folded.split())


def _matches_query(file_name: str, query_terms: list[str]) -> bool:
    """Match exact filename terms, with a small typo tolerance as fallback."""
    normalized_name = _fold_text(Path(file_name).stem)
    if all(term in normalized_name for term in query_terms):
        return True
    return all(
        len(term) >= 5
        and SequenceMatcher(None, term, normalized_name).ratio() >= 0.85
        for term in query_terms
    )


def _build_file_metadata(file_path: Path) -> dict[str, str | int]:
    """Build a lightweight metadata object for a located file."""
    suffix = file_path.suffix.lower()
    mime_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsm": "application/vnd.ms-excel.sheet.macroenabled.12",
    }
    return {
        "path": file_path.relative_to(FILES_ROOT).as_posix(),
        "name": file_path.name,
        "mime_type": mime_types.get(suffix, "application/octet-stream"),
        "size_bytes": file_path.stat().st_size,
    }


@mcp.tool()
def search_files(query: str, path: str = ".", max_results: int = 20) -> str:
    """Find Downloads files whose names contain the requested words.

    Args:
        query: Words or a phrase to find in file names.
        path: Downloads-relative directory in which to search.
        max_results: Maximum number of matching files to return.

    Returns:
        A concise list of Downloads-relative paths.
    """
    if not query.strip():
        return "Vui lòng cung cấp tên hoặc từ khóa nhận diện file."
    if not 1 <= max_results <= 100:
        return "max_results must be between 1 and 100."

    search_root = _safe_path(path)
    if not search_root.is_dir():
        return f"Không tìm thấy thư mục: {path}"

    query = _clean_query(query)
    query_terms = query.split()
    matches: list[str] = []
    for candidate in search_root.rglob("*"):
        if len(matches) >= max_results:
            break
        if not candidate.is_file() or _is_ignored(candidate):
            continue
        if _matches_query(candidate.name, query_terms):
            matches.append(candidate.relative_to(FILES_ROOT).as_posix())

    if not matches:
        return f"Không tìm thấy file phù hợp với: {query}"
    return "\n".join(matches)


@mcp.tool()
def locate_file(query: str, path: str = ".", max_results: int = 20) -> str:
    """Locate a file in Downloads and return a metadata payload for Gemini.

    This tool is intentionally file-first: it finds the matching file and returns
    its path, filename, MIME type, and size, without extracting file contents.
    Gemini can then inspect the original file directly using the returned metadata.

    Args:
        query: Words or a phrase to identify the file.
        path: Downloads-relative directory to search in.
        max_results: Maximum number of file metadata objects to return.

    Returns:
        JSON containing file metadata for the matched files.
    """
    if not query.strip():
        return "Vui lòng cung cấp tên hoặc từ khóa nhận diện file."
    if not 1 <= max_results <= 100:
        return "max_results must be between 1 and 100."

    search_root = _safe_path(path)
    if not search_root.is_dir():
        return f"Không tìm thấy thư mục: {path}"

    query = _clean_query(query)
    query_terms = query.split()
    matches: list[Path] = []
    for candidate in search_root.rglob("*"):
        if len(matches) >= max_results:
            break
        if not candidate.is_file() or _is_ignored(candidate):
            continue
        if _matches_query(candidate.name, query_terms):
            matches.append(candidate)

    if not matches:
        return f"Không tìm thấy file phù hợp với: {query}"

    import json

    return json.dumps(
        [
            _build_file_metadata(candidate)
            for candidate in matches
        ],
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def find_and_open_file(query: str, path: str = ".") -> str:
    """Find a uniquely matching Downloads file and open it on macOS.

    Use this as the single tool for any request to open a file. Extract the
    identifying words from the request and omit the extension and politeness.
    For example, "Mở file PDF HDSACOS cho ta" becomes the query "HDSACOS" and
    matches HDSACOS.pdf. If several files match, return their paths without
    opening one arbitrarily.

    Args:
        query: Words or a phrase from the requested file name.
        path: Downloads-relative directory in which to search.

    Returns:
        A status message, or a list when the request is ambiguous.
    """
    if not query.strip():
        return "Vui lòng cung cấp tên hoặc từ khóa nhận diện file."

    search_root = _safe_path(path)
    if not search_root.is_dir():
        return f"Không tìm thấy thư mục: {path}"

    query = _clean_query(query)
    query_terms = query.split()
    matches = [
        candidate
        for candidate in search_root.rglob("*")
        if candidate.is_file()
        and not _is_ignored(candidate)
        and _matches_query(candidate.name, query_terms)
    ]

    if not matches:
        return f"Không tìm thấy file phù hợp với: {query}"
    if len(matches) > 1:
        paths = [candidate.relative_to(FILES_ROOT).as_posix() for candidate in matches[:10]]
        return "Có nhiều file phù hợp. Hãy hỏi người dùng muốn chọn file nào:\n" + "\n".join(paths)

    return open_file(matches[0].relative_to(FILES_ROOT).as_posix())


@mcp.tool()
def manage_file(
    action: Literal["open", "read", "print", "delete"],
    query: str,
    path: str = ".",
    confirm: bool = False,
) -> str:
    """Interpret a natural-language file request and perform one safe action.

    The agent should extract only the identifying filename words into ``query``.
    For example, "in file PDF HDSACOS" becomes action ``print`` and query
    ``HDSACOS``. Ask the user for confirmation before retrying ``print`` or
    ``delete`` with ``confirm=True``.

    Args:
        action: One of open, read, print, or delete.
        query: Identifying words from the Downloads filename.
        path: Downloads-relative directory in which to search.
        confirm: Required for print and delete actions.

    Returns:
        The action result, an ambiguity list, or a confirmation request.
    """
    if not query.strip():
        return "Vui lòng cung cấp tên hoặc từ khóa nhận diện file."
    if action not in {"open", "read", "print", "delete"}:
        return f"Thao tác file không được hỗ trợ: {action}"
    if action in {"print", "delete"} and not confirm:
        verb = "print" if action == "print" else "delete"
        return f"CẦN_XÁC_NHẬN: Hãy hỏi người dùng xác nhận trước khi {verb} file phù hợp."

    search_root = _safe_path(path)
    if not search_root.is_dir():
        return f"Không tìm thấy thư mục: {path}"

    query_terms = _clean_query(query).split()
    matches = [
        candidate
        for candidate in search_root.rglob("*")
        if candidate.is_file()
        and not _is_ignored(candidate)
        and _matches_query(candidate.name, query_terms)
    ]
    if not matches:
        return f"Không tìm thấy file phù hợp với: {_clean_query(query)}"
    if len(matches) > 1:
        paths = [candidate.relative_to(FILES_ROOT).as_posix() for candidate in matches[:10]]
        return "Có nhiều file phù hợp. Hãy hỏi người dùng muốn chọn file nào:\n" + "\n".join(paths)

    file_path = matches[0]
    relative_path = file_path.relative_to(FILES_ROOT).as_posix()
    if action == "open":
        return open_file(relative_path)
    if action == "read":
        suffix = file_path.suffix.lower()
        if suffix == ".docx":
            return _read_word_file(file_path)
        if suffix == ".pdf":
            return _read_pdf_file(file_path)
        try:
            return file_path.read_text(encoding="utf-8")[:12000]
        except UnicodeDecodeError:
            return f"File này không phải văn bản thuần túy nên không thể đọc dạng chữ: {relative_path}"
    if action == "print":
        try:
            subprocess.Popen(["lp", str(file_path)])
        except OSError as error:
            return f"Không thể in {relative_path}: {error}"
        return f"Đã gửi {relative_path} đến máy in mặc định."

    trash_path = Path.home() / ".Trash" / file_path.name
    counter = 1
    while trash_path.exists():
        trash_path = Path.home() / ".Trash" / f"{file_path.stem} {counter}{file_path.suffix}"
        counter += 1
    shutil.move(str(file_path), str(trash_path))
    return f"Đã chuyển {relative_path} vào Thùng rác."


@mcp.tool()
def open_file(path: str) -> str:
    """Open one Downloads file with the macOS default application.

    Args:
        path: Downloads-relative path of the file to open.

    Returns:
        A status message describing whether the file was opened.
    """
    if platform.system() != "Darwin":
        return "Tính năng mở file hiện chỉ hỗ trợ macOS."

    file_path = _safe_path(path)
    if not file_path.is_file():
        return f"Không tìm thấy file: {path}"

    try:
        subprocess.Popen(["open", str(file_path)])
    except OSError as error:
        return f"Không thể mở {path}: {error}"
    return f"Đã mở {file_path.relative_to(FILES_ROOT).as_posix()}"


def _workbook_contains_query(file_path: Path, query_terms: list[str]) -> bool:
    """Return whether a workbook contains all query terms in any cell value."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return False

    try:
        workbook = load_workbook(
            filename=file_path,
            data_only=True,
            read_only=True,
        )
    except Exception:
        return False

    try:
        for worksheet in workbook.worksheets:
            for row in worksheet.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue
                    cell_text = _fold_text(str(cell.value))
                    if cell_text and all(term in cell_text for term in query_terms):
                        return True
        return False
    finally:
        workbook.close()


def _find_matching_excel_files(
    search_root: Path, query: str, search_content: bool = False
) -> list[Path]:
    """Find Excel files in a Downloads-relative directory.

    By default this matches on filename. When ``search_content`` is enabled, a
    second pass searches workbook cell values for the query terms.
    """
    query_terms = _clean_query(query).split()
    if not query_terms:
        return []

    excel_extensions = {".xlsx", ".xlsm"}

    filename_matches = [
        candidate
        for candidate in search_root.rglob("*")
        if candidate.is_file()
        and not _is_ignored(candidate)
        and candidate.suffix.lower() in excel_extensions
        and _matches_query(candidate.name, query_terms)
    ]

    if filename_matches or not search_content:
        return filename_matches

    content_matches = []
    for candidate in search_root.rglob("*"):
        if len(content_matches) >= 20:
            break
        if not candidate.is_file() or _is_ignored(candidate):
            continue
        if candidate.suffix.lower() not in excel_extensions:
            continue
        if _workbook_contains_query(candidate, query_terms):
            content_matches.append(candidate)

    return content_matches


def _docx_contains_query(file_path: Path, query_terms: list[str]) -> bool:
    """Return whether a DOCX file contains all query terms in its text."""
    try:
        from docx import Document
    except ImportError:
        return False

    try:
        document = Document(str(file_path))
    except Exception:
        return False

    fragments: list[str] = []
    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            fragments.append(paragraph.text)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    fragments.append(cell.text)

    content = _fold_text("\n".join(fragments))
    return all(term in content for term in query_terms)


def _find_matching_word_files(
    search_root: Path, query: str, search_content: bool = False
) -> list[Path]:
    """Find DOCX files by filename, or by workbook text when requested."""
    query_terms = _clean_query(query).split()
    if not query_terms:
        return []

    word_extensions = {".docx"}

    filename_matches = [
        candidate
        for candidate in search_root.rglob("*")
        if candidate.is_file()
        and not _is_ignored(candidate)
        and candidate.suffix.lower() in word_extensions
        and _matches_query(candidate.name, query_terms)
    ]

    if filename_matches or not search_content:
        return filename_matches

    content_matches = []
    for candidate in search_root.rglob("*"):
        if len(content_matches) >= 20:
            break
        if not candidate.is_file() or _is_ignored(candidate):
            continue
        if candidate.suffix.lower() not in word_extensions:
            continue
        if _docx_contains_query(candidate, query_terms):
            content_matches.append(candidate)

    return content_matches


def _pdf_contains_query(file_path: Path, query_terms: list[str]) -> bool:
    """Return whether a PDF file contains all query terms in its extracted text."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return False

    try:
        reader = PdfReader(str(file_path))
    except Exception:
        return False

    fragments = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            fragments.append(text)

    content = _fold_text("\n".join(fragments))
    return all(term in content for term in query_terms)


def _find_matching_pdf_files(
    search_root: Path, query: str, search_content: bool = False
) -> list[Path]:
    """Find PDF files by filename, or by extracted text when requested."""
    query_terms = _clean_query(query).split()
    if not query_terms:
        return []

    pdf_extensions = {".pdf"}

    filename_matches = [
        candidate
        for candidate in search_root.rglob("*")
        if candidate.is_file()
        and not _is_ignored(candidate)
        and candidate.suffix.lower() in pdf_extensions
        and _matches_query(candidate.name, query_terms)
    ]

    if filename_matches or not search_content:
        return filename_matches

    content_matches = []
    for candidate in search_root.rglob("*"):
        if len(content_matches) >= 20:
            break
        if not candidate.is_file() or _is_ignored(candidate):
            continue
        if candidate.suffix.lower() not in pdf_extensions:
            continue
        if _pdf_contains_query(candidate, query_terms):
            content_matches.append(candidate)

    return content_matches


def _read_word_file(file_path: Path) -> str:
    """Return the text contents of a DOCX file as structured JSON."""
    try:
        from docx import Document
    except ImportError:
        return "Chưa cài python-docx. Hãy chạy: uv add python-docx"

    try:
        document = Document(str(file_path))
    except Exception as error:
        return f"Không thể đọc file Word: {error}"

    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    tables = []
    for table in document.tables:
        rows = []
        for row in table.rows:
            row_values = [cell.text for cell in row.cells]
            if any(value.strip() for value in row_values):
                rows.append(row_values)
        if rows:
            tables.append(rows)

    import json

    return json.dumps(
        {
            "file": file_path.relative_to(FILES_ROOT).as_posix(),
            "paragraphs": paragraphs,
            "tables": tables,
        },
        ensure_ascii=False,
        indent=2,
    )


def _read_pdf_file(file_path: Path) -> str:
    """Return extracted text from a PDF file as structured JSON."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return "Chưa cài pypdf. Hãy chạy: uv add pypdf"

    try:
        reader = PdfReader(str(file_path))
    except Exception as error:
        return f"Không thể đọc file PDF: {error}"

    pages = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": page_index, "text": text})

    import json

    return json.dumps(
        {
            "file": file_path.relative_to(FILES_ROOT).as_posix(),
            "pages": pages,
        },
        ensure_ascii=False,
        indent=2,
    )


def _normalize_excel_value(value: str | int | float | bool | None):
    """Coerce user-provided scalar values into a workbook-friendly type."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return ""
        lowered = stripped.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            if "." in stripped or "e" in lowered:
                return float(stripped)
            return int(stripped)
        except ValueError:
            return stripped
    return value


def _parse_numeric_value(value: object) -> float:
    """Convert Excel cell contents to a numeric value for arithmetic operations."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        raise ValueError("Boolean values cannot be used in arithmetic operations.")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(" ", "")
        for token in ("đ", "₫", "$", ","):
            stripped = stripped.replace(token, "")
        if stripped == "":
            return 0.0
        try:
            return float(stripped)
        except ValueError as error:
            raise ValueError(f"Cannot use '{value}' in arithmetic operations.") from error
    raise ValueError(f"Cannot use '{value}' in arithmetic operations.")


@mcp.tool()
def read_excel(
    query: str,
    path: str = ".",
    max_rows: int = 200,
    max_columns: int = 30,
) -> str:
    """Read an Excel workbook and return its contents as structured JSON.

    Use this when the user asks about information inside an Excel file,
    such as prices, quantities, materials, names, totals, or other table data.

    The user does not need to say "Excel". For example:
    "Trong bảng báo giá đó xi măng giá bao nhiêu?"
    can be handled by this tool.

    Args:
        query: Identifying words from the Excel filename.
        path: Downloads-relative directory in which to search.
        max_rows: Maximum rows returned per sheet.
        max_columns: Maximum columns returned per sheet.

    Returns:
        Structured JSON containing workbook sheets, row numbers,
        cell coordinates, and values.
    """
    if not query.strip():
        return "Vui lòng cung cấp tên hoặc từ khóa nhận diện file Excel."

    if not 1 <= max_rows <= 1000:
        return "max_rows must be between 1 and 1000."

    if not 1 <= max_columns <= 100:
        return "max_columns must be between 1 and 100."

    try:
        from openpyxl import load_workbook
    except ImportError:
        return "Chưa cài openpyxl. Hãy chạy: pip install openpyxl"

    search_root = _safe_path(path)
    if not search_root.is_dir():
        return f"Không tìm thấy thư mục: {path}"

    matches = _find_matching_excel_files(search_root, query, search_content=True)

    if not matches:
        return f"Không tìm thấy file Excel phù hợp với: {_clean_query(query)}"

    if len(matches) > 1:
        paths = [
            candidate.relative_to(FILES_ROOT).as_posix()
            for candidate in matches[:10]
        ]
        return (
            "Có nhiều file Excel phù hợp. "
            "Hãy hỏi người dùng muốn chọn file nào:\n"
            + "\n".join(paths)
        )

    file_path = matches[0]

    try:
        workbook = load_workbook(
            filename=file_path,
            data_only=True,
            read_only=True,
        )
    except Exception as error:
        return f"Không thể đọc file Excel: {error}"

    result = {
        "file": file_path.relative_to(FILES_ROOT).as_posix(),
        "sheets": [],
    }

    try:
        for worksheet in workbook.worksheets:
            rows = []
            for row_index, row in enumerate(
                worksheet.iter_rows(
                    min_row=1,
                    max_row=max_rows,
                    max_col=max_columns,
                ),
                start=1,
            ):
                cells = {}
                for cell in row:
                    if cell.value is not None:
                        cells[cell.column_letter] = cell.value

                if cells:
                    rows.append({"row": row_index, "cells": cells})

            result["sheets"].append(
                {
                    "name": worksheet.title,
                    "rows": rows,
                }
            )
    finally:
        workbook.close()

    import json

    return json.dumps(
        result,
        ensure_ascii=False,
        default=str,
        indent=2,
    )


@mcp.tool()
def read_word(
    query: str,
    path: str = ".",
) -> str:
    """Read a DOCX file and return its text content as JSON.

    Use this when the user asks about information inside a Word document.
    This tool can search either by filename or by content inside the document.

    Args:
        query: Identifying words from the DOCX filename or document content.
        path: Downloads-relative directory in which to search.

    Returns:
        Structured JSON containing paragraphs and tables from the matching document.
    """
    if not query.strip():
        return "Vui lòng cung cấp tên hoặc từ khóa nhận diện file Word."

    search_root = _safe_path(path)
    if not search_root.is_dir():
        return f"Không tìm thấy thư mục: {path}"

    matches = _find_matching_word_files(search_root, query, search_content=True)
    if not matches:
        return f"Không tìm thấy file Word phù hợp với: {_clean_query(query)}"
    if len(matches) > 1:
        paths = [candidate.relative_to(FILES_ROOT).as_posix() for candidate in matches[:10]]
        return "Có nhiều file Word phù hợp. Hãy hỏi người dùng muốn chọn file nào:\n" + "\n".join(paths)

    return _read_word_file(matches[0])


@mcp.tool()
def edit_word(
    query: str,
    old_text: str,
    new_text: str,
    path: str = ".",
) -> str:
    """Replace text inside a DOCX file and save the result.

    This tool is similar to Excel editing: Gemini decides what to change, while
    MCP performs the actual write and verification.

    Args:
        query: Identifying words from the DOCX filename or document content.
        old_text: Exact text to replace inside the Word document.
        new_text: Replacement text.
        path: Downloads-relative directory in which to search.

    Returns:
        JSON describing the change and verification result.
    """
    if not query.strip():
        return "Vui lòng cung cấp tên hoặc từ khóa nhận diện file Word."
    if not old_text.strip():
        return "old_text là bắt buộc để xác định đoạn văn bản cần sửa."

    search_root = _safe_path(path)
    if not search_root.is_dir():
        return f"Không tìm thấy thư mục: {path}"

    matches = _find_matching_word_files(search_root, query, search_content=True)
    if not matches:
        return f"Không tìm thấy file Word phù hợp với: {_clean_query(query)}"
    if len(matches) > 1:
        paths = [candidate.relative_to(FILES_ROOT).as_posix() for candidate in matches[:10]]
        return "Có nhiều file Word phù hợp. Hãy hỏi người dùng muốn chọn file nào:\n" + "\n".join(paths)

    try:
        from docx import Document
    except ImportError:
        return "Chưa cài python-docx. Hãy chạy: uv add python-docx"

    file_path = matches[0]
    document = Document(str(file_path))
    replacement_count = 0

    for paragraph in document.paragraphs:
        occurrences = paragraph.text.count(old_text)
        if occurrences:
            paragraph.text = paragraph.text.replace(old_text, new_text)
            replacement_count += occurrences

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                occurrences = cell.text.count(old_text)
                if occurrences:
                    cell.text = cell.text.replace(old_text, new_text)
                    replacement_count += occurrences

    if replacement_count == 0:
        return f"Không tìm thấy đoạn văn bản '{old_text}' trong file Word phù hợp."

    document.save(str(file_path))

    verify_document = Document(str(file_path))
    verify_fragments = [paragraph.text for paragraph in verify_document.paragraphs]
    verify_fragments.extend(
        cell.text
        for table in verify_document.tables
        for row in table.rows
        for cell in row.cells
    )
    verify_text = "\n".join(verify_fragments)

    import json

    return json.dumps(
        {
            "status": "updated",
            "file": file_path.relative_to(FILES_ROOT).as_posix(),
            "old_text": old_text,
            "new_text": new_text,
            "replaced_occurrences": replacement_count,
            "verified_contains_old_text": old_text in verify_text,
            "verified_contains_new_text": new_text in verify_text,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def read_pdf(
    query: str,
    path: str = ".",
    max_pages: int = 50,
) -> str:
    """Read a PDF file and return its extracted text as JSON.

    This tool is read-only: it can search the PDF by filename or by extracted text,
    then return the text content page by page for the user to answer from.

    Args:
        query: Identifying words from the PDF filename or document content.
        path: Downloads-relative directory in which to search.
        max_pages: Maximum number of pages to extract.

    Returns:
        Structured JSON containing the PDF file and extracted page text.
    """
    if not query.strip():
        return "Vui lòng cung cấp tên hoặc từ khóa nhận diện file PDF."
    if not 1 <= max_pages <= 200:
        return "max_pages must be between 1 and 200."

    search_root = _safe_path(path)
    if not search_root.is_dir():
        return f"Không tìm thấy thư mục: {path}"

    matches = _find_matching_pdf_files(search_root, query, search_content=True)
    if not matches:
        return f"Không tìm thấy file PDF phù hợp với: {_clean_query(query)}"
    if len(matches) > 1:
        paths = [candidate.relative_to(FILES_ROOT).as_posix() for candidate in matches[:10]]
        return "Có nhiều file PDF phù hợp. Hãy hỏi người dùng muốn chọn file nào:\n" + "\n".join(paths)

    return _read_pdf_file(matches[0])


@mcp.tool()
def edit_excel(
    query: str,
    cell: str,
    operation: str = "set",
    value: str | int | float | bool | None = None,
    sheet: str | None = None,
    path: str = ".",
) -> str:
    """Edit a cell in an Excel workbook, save the file, and verify the result.

    This tool keeps Gemini responsible for understanding the workbook and deciding
    the target change, while MCP performs the actual write operation. The tool
    follows the safe pattern: read target → modify → save → reopen → verify.

    Args:
        query: Identifying words from the Excel filename.
        cell: The target cell coordinate, for example D2 or A10.
        operation: One of set, add, subtract, or multiply.
        value: The value to write or apply.
        sheet: Optional sheet name. Defaults to the first sheet.
        path: Downloads-relative directory in which to search.

    Returns:
        JSON describing the file, cell, operation, and verified final value.
    """
    if not query.strip():
        return "Vui lòng cung cấp tên hoặc từ khóa nhận diện file Excel."

    if not cell or not cell.strip():
        return "cell là bắt buộc để xác định ô sẽ sửa."

    operation = operation.lower()
    if operation not in {"set", "add", "subtract", "multiply"}:
        return "operation phải là một trong: set, add, subtract, multiply."

    try:
        from openpyxl import load_workbook
    except ImportError:
        return "Chưa cài openpyxl. Hãy chạy: pip install openpyxl"

    search_root = _safe_path(path)
    if not search_root.is_dir():
        return f"Không tìm thấy thư mục: {path}"

    matches = _find_matching_excel_files(search_root, query)
    if not matches:
        return f"Không tìm thấy file Excel phù hợp với: {_clean_query(query)}"

    if len(matches) > 1:
        paths = [
            candidate.relative_to(FILES_ROOT).as_posix()
            for candidate in matches[:10]
        ]
        return (
            "Có nhiều file Excel phù hợp. "
            "Hãy hỏi người dùng muốn chọn file nào:\n"
            + "\n".join(paths)
        )

    file_path = matches[0]

    try:
        workbook = load_workbook(filename=file_path, data_only=False)
    except Exception as error:
        return f"Không thể mở file Excel để sửa: {error}"

    try:
        if sheet:
            if sheet not in workbook.sheetnames:
                raise ValueError(f"Không tìm thấy sheet '{sheet}'.")
            worksheet = workbook[sheet]
        else:
            worksheet = workbook[workbook.sheetnames[0]]

        target_cell = worksheet[cell]
        previous_value = target_cell.value

        normalized_value = _normalize_excel_value(value)

        if operation == "set":
            worksheet[cell] = normalized_value
            requested_value = normalized_value
        else:
            if value is None:
                raise ValueError("value là bắt buộc khi operation là add/subtract/multiply.")

            if operation == "add":
                worksheet[cell] = _parse_numeric_value(previous_value) + _parse_numeric_value(
                    normalized_value
                )
            elif operation == "subtract":
                worksheet[cell] = _parse_numeric_value(previous_value) - _parse_numeric_value(
                    normalized_value
                )
            else:
                worksheet[cell] = _parse_numeric_value(previous_value) * _parse_numeric_value(
                    normalized_value
                )

            requested_value = normalized_value

        workbook.save(file_path)

        verify_workbook = load_workbook(
            filename=file_path,
            data_only=True,
            read_only=True,
        )
        verify_worksheet = verify_workbook[worksheet.title]
        final_value = verify_worksheet[cell].value
        verify_workbook.close()

        import json

        return json.dumps(
            {
                "status": "updated",
                "file": file_path.relative_to(FILES_ROOT).as_posix(),
                "sheet": worksheet.title,
                "cell": cell,
                "operation": operation,
                "previous_value": previous_value,
                "requested_value": requested_value,
                "verified_value": final_value,
            },
            ensure_ascii=False,
            default=str,
            indent=2,
        )
    except Exception as error:
        workbook.close()
        return f"Không thể sửa file Excel: {error}"


if __name__ == "__main__":
    mcp.run(transport="stdio")