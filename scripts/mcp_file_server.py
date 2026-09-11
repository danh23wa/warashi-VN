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


if __name__ == "__main__":
    mcp.run(transport="stdio")