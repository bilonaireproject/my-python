"""Utility functions with no non-trivial dependencies."""

from __future__ import annotations

import hashlib
import io
import os
import pathlib
import re
import shutil
import sys
import time
from importlib import resources as importlib_resources
from typing import IO, Callable, Container, Final, Iterable, Sequence, Sized, TypeVar
from typing_extensions import Literal

try:
    import curses

    import _curses  # noqa: F401

    CURSES_ENABLED = True
except ImportError:
    CURSES_ENABLED = False

T = TypeVar("T")

if sys.version_info >= (3, 9):
    TYPESHED_DIR: Final = str(importlib_resources.files("mypy") / "typeshed")
else:
    with importlib_resources.path(
        "mypy",  # mypy-c doesn't support __package__
        "py.typed",  # a marker file for type information, we assume typeshed to live in the same dir
    ) as _resource:
        TYPESHED_DIR = str(_resource.parent / "typeshed")


ENCODING_RE: Final = re.compile(rb"([ \t\v]*#.*(\r\n?|\n))??[ \t\v]*#.*coding[:=][ \t]*([-\w.]+)")

DEFAULT_SOURCE_OFFSET: Final = 4
DEFAULT_COLUMNS: Final = 80

# At least this number of columns will be shown on each side of
# error location when printing source code snippet.
MINIMUM_WIDTH: Final = 20

# VT100 color code processing was added in Windows 10, but only the second major update,
# Threshold 2. Fortunately, everyone (even on LTSB, Long Term Support Branch) should
# have a version of Windows 10 newer than this. Note that Windows 8 and below are not
# supported, but are either going out of support, or make up only a few % of the market.
MINIMUM_WINDOWS_MAJOR_VT100: Final = 10
MINIMUM_WINDOWS_BUILD_VT100: Final = 10586

SPECIAL_DUNDERS: Final = frozenset(
    ("__init__", "__new__", "__call__", "__init_subclass__", "__class_getitem__")
)


def is_dunder(name: str, exclude_special: bool = False) -> bool:
    """Returns whether name is a dunder name.

    Args:
        exclude_special: Whether to return False for a couple special dunder methods.

    """
    if exclude_special and name in SPECIAL_DUNDERS:
        return False
    return name.startswith("__") and name.endswith("__")


def is_sunder(name: str) -> bool:
    return not is_dunder(name) and name.startswith("_") and name.endswith("_")


def split_module_names(mod_name: str) -> list[str]:
    """Return the module and all parent module names.

    So, if `mod_name` is 'a.b.c', this function will return
    ['a.b.c', 'a.b', and 'a'].
    """
    out = [mod_name]
    while "." in mod_name:
        mod_name = mod_name.rsplit(".", 1)[0]
        out.append(mod_name)
    return out


def module_prefix(modules: Iterable[str], target: str) -> str | None:
    result = split_target(modules, target)
    if result is None:
        return None
    return result[0]


def split_target(modules: Iterable[str], target: str) -> tuple[str, str] | None:
    remaining: list[str] = []
    while True:
        if target in modules:
            return target, ".".join(remaining)
        components = target.rsplit(".", 1)
        if len(components) == 1:
            return None
        target = components[0]
        remaining.insert(0, components[1])


def short_type(obj: object) -> str:
    """Return the last component of the type name of an object.

    If obj is None, return 'nil'. For example, if obj is 1, return 'int'.
    """
    if obj is None:
        return "nil"
    t = str(type(obj))
    return t.split(".")[-1].rstrip("'>")


def find_python_encoding(text: bytes) -> tuple[str, int]:
    """PEP-263 for detecting Python file encoding"""
    result = ENCODING_RE.match(text)
    if result:
        line = 2 if result.group(1) else 1
        encoding = result.group(3).decode("ascii")
        # Handle some aliases that Python is happy to accept and that are used in the wild.
        if encoding.startswith(("iso-latin-1-", "latin-1-")) or encoding == "iso-latin-1":
            encoding = "latin-1"
        return encoding, line
    else:
        default_encoding = "utf8"
        return default_encoding, -1


def bytes_to_human_readable_repr(b: bytes) -> str:
    """Converts bytes into some human-readable representation. Unprintable
    bytes such as the nul byte are escaped. For example:

        >>> b = bytes([102, 111, 111, 10, 0])
        >>> s = bytes_to_human_readable_repr(b)
        >>> print(s)
        foo\n\x00
        >>> print(repr(s))
        'foo\\n\\x00'
    """
    return repr(b)[2:-1]


class DecodeError(Exception):
    """Exception raised when a file cannot be decoded due to an unknown encoding type.

    Essentially a wrapper for the LookupError raised by `bytearray.decode`
    """


def decode_python_encoding(source: bytes) -> str:
    """Read the Python file with while obeying PEP-263 encoding detection.

    Returns the source as a string.
    """
    # check for BOM UTF-8 encoding and strip it out if present
    if source.startswith(b"\xef\xbb\xbf"):
        encoding = "utf8"
        source = source[3:]
    else:
        # look at first two lines and check if PEP-263 coding is present
        encoding, _ = find_python_encoding(source)

    try:
        source_text = source.decode(encoding)
    except LookupError as lookuperr:
        raise DecodeError(str(lookuperr)) from lookuperr
    return source_text


def read_py_file(path: str, read: Callable[[str], bytes]) -> list[str] | None:
    """Try reading a Python file as list of source lines.

    Return None if something goes wrong.
    """
    try:
        source = read(path)
    except OSError:
        return None
    else:
        try:
            source_lines = decode_python_encoding(source).splitlines()
        except DecodeError:
            return None
        return source_lines


def trim_source_line(line: str, max_len: int, col: int, min_width: int) -> tuple[str, int]:
    """Trim a line of source code to fit into max_len.

    Show 'min_width' characters on each side of 'col' (an error location). If either
    start or end is trimmed, this is indicated by adding '...' there.
    A typical result looks like this:
        ...some_variable = function_to_call(one_arg, other_arg) or...

    Return the trimmed string and the column offset to to adjust error location.
    """
    if max_len < 2 * min_width + 1:
        # In case the window is too tiny it is better to still show something.
        max_len = 2 * min_width + 1

    # Trivial case: line already fits in.
    if len(line) <= max_len:
        return line, 0

    # If column is not too large so that there is still min_width after it,
    # the line doesn't need to be trimmed at the start.
    if col + min_width < max_len:
        return line[:max_len] + "...", 0

    # Otherwise, if the column is not too close to the end, trim both sides.
    if col < len(line) - min_width - 1:
        offset = col - max_len + min_width + 1
        return "..." + line[offset : col + min_width + 1] + "...", offset - 3

    # Finally, if the column is near the end, just trim the start.
    return "..." + line[-max_len:], len(line) - max_len - 3


def get_mypy_comments(source: str) -> list[tuple[int, str]]:
    PREFIX = "# mypy: "
    # Don't bother splitting up the lines unless we know it is useful
    if PREFIX not in source:
        return []
    lines = source.split("\n")
    results = []
    for i, line in enumerate(lines):
        if line.startswith(PREFIX):
            results.append((i + 1, line[len(PREFIX) :]))

    return results


JUNIT_HEADER_TEMPLATE: Final = """<?xml version="1.0" encoding="utf-8"?>
<testsuite errors="{errors}" failures="{failures}" name="mypy" skips="0" tests="{tests}" time="{time:.3f}">
"""

JUNIT_TESTCASE_FAIL_TEMPLATE: Final = """  <testcase classname="mypy" file="{filename}" line="1" name="{name}" time="{time:.3f}">
    <failure message="mypy produced messages">{text}</failure>
  </testcase>
"""

JUNIT_ERROR_TEMPLATE: Final = """  <testcase classname="mypy" file="mypy" line="1" name="mypy-py{ver}-{platform}" time="{time:.3f}">
    <error message="mypy produced errors">{text}</error>
  </testcase>
"""

JUNIT_TESTCASE_PASS_TEMPLATE: Final = """  <testcase classname="mypy" file="mypy" line="1" name="mypy-py{ver}-{platform}" time="{time:.3f}">
  </testcase>
"""

JUNIT_FOOTER: Final = """</testsuite>
"""


def _generate_junit_contents(
    dt: float,
    serious: bool,
    messages_by_file: dict[str | None, list[str]],
    version: str,
    platform: str,
) -> str:
    from xml.sax.saxutils import escape

    if serious:
        failures = 0
        errors = len(messages_by_file)
    else:
        failures = len(messages_by_file)
        errors = 0

    xml = JUNIT_HEADER_TEMPLATE.format(
        errors=errors,
        failures=failures,
        time=dt,
        # If there are no messages, we still write one "test" indicating success.
        tests=len(messages_by_file) or 1,
    )

    if not messages_by_file:
        xml += JUNIT_TESTCASE_PASS_TEMPLATE.format(time=dt, ver=version, platform=platform)
    else:
        for filename, messages in messages_by_file.items():
            if filename is not None:
                xml += JUNIT_TESTCASE_FAIL_TEMPLATE.format(
                    text=escape("\n".join(messages)),
                    filename=filename,
                    time=dt,
                    name="mypy-py{ver}-{platform} {filename}".format(
                        ver=version, platform=platform, filename=filename
                    ),
                )
            else:
                xml += JUNIT_TESTCASE_FAIL_TEMPLATE.format(
                    text=escape("\n".join(messages)),
                    filename="mypy",
                    time=dt,
                    name="mypy-py{ver}-{platform}".format(ver=version, platform=platform),
                )

    xml += JUNIT_FOOTER

    return xml


def write_junit_xml(
    dt: float,
    serious: bool,
    messages_by_file: dict[str | None, list[str]],
    path: str,
    version: str,
    platform: str,
) -> None:
    xml = _generate_junit_contents(dt, serious, messages_by_file, version, platform)

    # creates folders if needed
    xml_dirs = os.path.dirname(os.path.abspath(path))
    os.makedirs(xml_dirs, exist_ok=True)

    with open(path, "wb") as f:
        f.write(xml.encode("utf-8"))


class IdMapper:
    """Generate integer ids for objects.

    Unlike id(), these start from 0 and increment by 1, and ids won't
    get reused across the life-time of IdMapper.

    Assume objects don't redefine __eq__ or __hash__.
    """

    def __init__(self) -> None:
        self.id_map: dict[object, int] = {}
        self.next_id = 0

    def id(self, o: object) -> int:
        if o not in self.id_map:
            self.id_map[o] = self.next_id
            self.next_id += 1
        return self.id_map[o]


def get_prefix(fullname: str) -> str:
    """Drop the final component of a qualified name (e.g. ('x.y' -> 'x')."""
    return fullname.rsplit(".", 1)[0]


def correct_relative_import(
    cur_mod_id: str, relative: int, target: str, is_cur_package_init_file: bool
) -> tuple[str, bool]:
    if relative == 0:
        return target, True
    parts = cur_mod_id.split(".")
    rel = relative
    if is_cur_package_init_file:
        rel -= 1
    ok = len(parts) >= rel
    if rel != 0:
        cur_mod_id = ".".join(parts[:-rel])
    return cur_mod_id + (("." + target) if target else ""), ok


fields_cache: Final[dict[type[object], list[str]]] = {}


def get_class_descriptors(cls: type[object]) -> Sequence[str]:
    import inspect  # Lazy import for minor startup speed win

    # Maintain a cache of type -> attributes defined by descriptors in the class
    # (that is, attributes from __slots__ and C extension classes)
    if cls not in fields_cache:
        members = inspect.getmembers(
            cls, lambda o: inspect.isgetsetdescriptor(o) or inspect.ismemberdescriptor(o)
        )
        fields_cache[cls] = [x for x, y in members if x != "__weakref__" and x != "__dict__"]
    return fields_cache[cls]


def replace_object_state(
    new: object, old: object, copy_dict: bool = False, skip_slots: tuple[str, ...] = ()
) -> None:
    """Copy state of old node to the new node.

    This handles cases where there is __dict__ and/or attribute descriptors
    (either from slots or because the type is defined in a C extension module).

    Assume that both objects have the same __class__.
    """
    if hasattr(old, "__dict__"):
        if copy_dict:
            new.__dict__ = dict(old.__dict__)
        else:
            new.__dict__ = old.__dict__

    for attr in get_class_descriptors(old.__class__):
        if attr in skip_slots:
            continue
        try:
            if hasattr(old, attr):
                setattr(new, attr, getattr(old, attr))
            elif hasattr(new, attr):
                delattr(new, attr)
        # There is no way to distinguish getsetdescriptors that allow
        # writes from ones that don't (I think?), so we just ignore
        # AttributeErrors if we need to.
        # TODO: What about getsetdescriptors that act like properties???
        except AttributeError:
            pass


def is_sub_path(path1: str, path2: str) -> bool:
    """Given two paths, return if path1 is a sub-path of path2."""
    return pathlib.Path(path2) in pathlib.Path(path1).parents


def hard_exit(status: int = 0) -> None:
    """Kill the current process without fully cleaning up.

    This can be quite a bit faster than a normal exit() since objects are not freed.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)


def unmangle(name: str) -> str:
    """Remove internal suffixes from a short name."""
    return name.rstrip("'")


def get_unique_redefinition_name(name: str, existing: Container[str]) -> str:
    """Get a simple redefinition name not present among existing.

    For example, for name 'foo' we try 'foo-redefinition', 'foo-redefinition2',
    'foo-redefinition3', etc. until we find one that is not in existing.
    """
    r_name = name + "-redefinition"
    if r_name not in existing:
        return r_name

    i = 2
    while r_name + str(i) in existing:
        i += 1
    return r_name + str(i)


def check_python_version(program: str) -> None:
    """Report issues with the Python used to run mypy, dmypy, or stubgen"""
    # Check for known bad Python versions.
    if sys.version_info[:2] < (3, 8):  # noqa: UP036
        sys.exit(
            "Running {name} with Python 3.7 or lower is not supported; "
            "please upgrade to 3.8 or newer".format(name=program)
        )


def count_stats(messages: list[str]) -> tuple[int, int, int]:
    """Count total number of errors, notes and error_files in message list."""
    errors = [e for e in messages if ": error:" in e]
    error_files = {e.split(":")[0] for e in errors}
    notes = [e for e in messages if ": note:" in e]
    return len(errors), len(notes), len(error_files)


def split_words(msg: str) -> list[str]:
    """Split line of text into words (but not within quoted groups)."""
    next_word = ""
    res: list[str] = []
    allow_break = True
    for c in msg:
        if c == " " and allow_break:
            res.append(next_word)
            next_word = ""
            continue
        if c == '"':
            allow_break = not allow_break
        next_word += c
    res.append(next_word)
    return res


def get_terminal_width() -> int:
    """Get current terminal width if possible, otherwise return the default one."""
    return (
        int(os.getenv("MYPY_FORCE_TERMINAL_WIDTH", "0"))
        or shutil.get_terminal_size().columns
        or DEFAULT_COLUMNS
    )


def soft_wrap(msg: str, max_len: int, first_offset: int, num_indent: int = 0) -> str:
    """Wrap a long error message into few lines.

    Breaks will only happen between words, and never inside a quoted group
    (to avoid breaking types such as "Union[int, str]"). The 'first_offset' is
    the width before the start of first line.

    Pad every next line with 'num_indent' spaces. Every line will be at most 'max_len'
    characters, except if it is a single word or quoted group.

    For example:
               first_offset
        ------------------------
        path/to/file: error: 58: Some very long error message
            that needs to be split in separate lines.
            "Long[Type, Names]" are never split.
        ^^^^--------------------------------------------------
        num_indent           max_len
    """
    words = split_words(msg)
    next_line = words.pop(0)
    lines: list[str] = []
    while words:
        next_word = words.pop(0)
        max_line_len = max_len - num_indent if lines else max_len - first_offset
        # Add 1 to account for space between words.
        if len(next_line) + len(next_word) + 1 <= max_line_len:
            next_line += " " + next_word
        else:
            lines.append(next_line)
            next_line = next_word
    lines.append(next_line)
    padding = "\n" + " " * num_indent
    return padding.join(lines)


def hash_digest(data: bytes) -> str:
    """Compute a hash digest of some data.

    We use a cryptographic hash because we want a low probability of
    accidental collision, but we don't really care about any of the
    cryptographic properties.
    """
    # Once we drop Python 3.5 support, we should consider using
    # blake2b, which is faster.
    return hashlib.sha256(data).hexdigest()


def parse_gray_color(cup: bytes) -> str:
    """Reproduce a gray color in ANSI escape sequence"""
    if sys.platform == "win32":
        assert False, "curses is not available on Windows"
    set_color = "".join([cup[:-1].decode(), "m"])
    gray = curses.tparm(set_color.encode("utf-8"), 1, 9).decode()
    return gray


def should_force_color() -> bool:
    env_var = os.getenv("MYPY_FORCE_COLOR", os.getenv("FORCE_COLOR", "0"))
    try:
        return bool(int(env_var))
    except ValueError:
        return bool(env_var)


class FancyFormatter:
    """Apply color and bold font to terminal output.

    This currently only works on Linux and Mac.
    """

    def __init__(self, f_out: IO[str], f_err: IO[str], hide_error_codes: bool) -> None:
        self.hide_error_codes = hide_error_codes
        # Check if we are in a human-facing terminal on a supported platform.
        if sys.platform not in ("linux", "darwin", "win32", "emscripten"):
            self.dummy_term = True
            return
        if not should_force_color() and (not f_out.isatty() or not f_err.isatty()):
            self.dummy_term = True
            return
        if sys.platform == "win32":
            self.dummy_term = not self.initialize_win_colors()
        elif sys.platform == "emscripten":
            self.dummy_term = not self.initialize_vt100_colors()
        else:
            self.dummy_term = not self.initialize_unix_colors()
        if not self.dummy_term:
            self.colors = {
                "red": self.RED,
                "green": self.GREEN,
                "blue": self.BLUE,
                "yellow": self.YELLOW,
                "none": "",
            }

    def initialize_vt100_colors(self) -> bool:
        """Return True if initialization was successful and we can use colors, False otherwise"""
        # Windows and Emscripten can both use ANSI/VT100 escape sequences for color
        assert sys.platform in ("win32", "emscripten")
        self.BOLD = "\033[1m"
        self.UNDER = "\033[4m"
        self.BLUE = "\033[94m"
        self.GREEN = "\033[92m"
        self.RED = "\033[91m"
        self.YELLOW = "\033[93m"
        self.NORMAL = "\033[0m"
        self.DIM = "\033[2m"
        return True

    def initialize_win_colors(self) -> bool:
        """Return True if initialization was successful and we can use colors, False otherwise"""
        # Windows ANSI escape sequences are only supported on Threshold 2 and above.
        # we check with an assert at runtime and an if check for mypy, as asserts do not
        # yet narrow platform
        assert sys.platform == "win32"
        if sys.platform == "win32":
            winver = sys.getwindowsversion()
            if (
                winver.major < MINIMUM_WINDOWS_MAJOR_VT100
                or winver.build < MINIMUM_WINDOWS_BUILD_VT100
            ):
                return False
            import ctypes

            kernel32 = ctypes.windll.kernel32
            ENABLE_PROCESSED_OUTPUT = 0x1
            ENABLE_WRAP_AT_EOL_OUTPUT = 0x2
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x4
            STD_OUTPUT_HANDLE = -11
            kernel32.SetConsoleMode(
                kernel32.GetStdHandle(STD_OUTPUT_HANDLE),
                ENABLE_PROCESSED_OUTPUT
                | ENABLE_WRAP_AT_EOL_OUTPUT
                | ENABLE_VIRTUAL_TERMINAL_PROCESSING,
            )
            self.initialize_vt100_colors()
            return True
        return False

    def initialize_unix_colors(self) -> bool:
        """Return True if initialization was successful and we can use colors, False otherwise"""
        if sys.platform == "win32" or not CURSES_ENABLED:
            return False
        try:
            # setupterm wants a fd to potentially write an "initialization sequence".
            # We override sys.stdout for the daemon API so if stdout doesn't have an fd,
            # just give it /dev/null.
            try:
                fd = sys.stdout.fileno()
            except io.UnsupportedOperation:
                with open("/dev/null", "rb") as f:
                    curses.setupterm(fd=f.fileno())
            else:
                curses.setupterm(fd=fd)
        except curses.error:
            # Most likely terminfo not found.
            return False
        bold = curses.tigetstr("bold")
        under = curses.tigetstr("smul")
        set_color = curses.tigetstr("setaf")
        set_eseq = curses.tigetstr("cup")
        normal = curses.tigetstr("sgr0")

        if not (bold and under and set_color and set_eseq and normal):
            return False

        self.NORMAL = normal.decode()
        self.BOLD = bold.decode()
        self.UNDER = under.decode()
        self.DIM = parse_gray_color(set_eseq)
        self.BLUE = curses.tparm(set_color, curses.COLOR_BLUE).decode()
        self.GREEN = curses.tparm(set_color, curses.COLOR_GREEN).decode()
        self.RED = curses.tparm(set_color, curses.COLOR_RED).decode()
        self.YELLOW = curses.tparm(set_color, curses.COLOR_YELLOW).decode()
        return True

    def style(
        self,
        text: str,
        color: Literal["red", "green", "blue", "yellow", "none"],
        bold: bool = False,
        underline: bool = False,
        dim: bool = False,
    ) -> str:
        """Apply simple color and style (underlined or bold)."""
        if self.dummy_term:
            return text
        if bold:
            start = self.BOLD
        else:
            start = ""
        if underline:
            start += self.UNDER
        if dim:
            start += self.DIM
        return start + self.colors[color] + text + self.NORMAL

    def fit_in_terminal(
        self, messages: list[str], fixed_terminal_width: int | None = None
    ) -> list[str]:
        """Improve readability by wrapping error messages and trimming source code."""
        width = fixed_terminal_width or get_terminal_width()
        new_messages = messages.copy()
        for i, error in enumerate(messages):
            if ": error:" in error:
                loc, msg = error.split("error:", maxsplit=1)
                msg = soft_wrap(msg, width, first_offset=len(loc) + len("error: "))
                new_messages[i] = loc + "error:" + msg
            if error.startswith(" " * DEFAULT_SOURCE_OFFSET) and "^" not in error:
                # TODO: detecting source code highlights through an indent can be surprising.
                # Restore original error message and error location.
                error = error[DEFAULT_SOURCE_OFFSET:]
                marker_line = messages[i + 1]
                marker_column = marker_line.index("^")
                column = marker_column - DEFAULT_SOURCE_OFFSET
                if "~" not in marker_line:
                    marker = "^"
                else:
                    # +1 because both ends are included
                    marker = marker_line[marker_column : marker_line.rindex("~") + 1]

                # Let source have some space also on the right side, plus 6
                # to accommodate ... on each side.
                max_len = width - DEFAULT_SOURCE_OFFSET - 6
                source_line, offset = trim_source_line(error, max_len, column, MINIMUM_WIDTH)

                new_messages[i] = " " * DEFAULT_SOURCE_OFFSET + source_line
                # Also adjust the error marker position and trim error marker is needed.
                new_marker_line = " " * (DEFAULT_SOURCE_OFFSET + column - offset) + marker
                if len(new_marker_line) > len(new_messages[i]) and len(marker) > 3:
                    new_marker_line = new_marker_line[: len(new_messages[i]) - 3] + "..."
                new_messages[i + 1] = new_marker_line
        return new_messages

    def colorize(self, error: str) -> str:
        """Colorize an output line by highlighting the status and error code."""
        if ": error:" in error:
            loc, msg = error.split("error:", maxsplit=1)
            if self.hide_error_codes:
                return (
                    loc + self.style("error:", "red", bold=True) + self.highlight_quote_groups(msg)
                )
            codepos = msg.rfind("[")
            if codepos != -1:
                code = msg[codepos:]
                msg = msg[:codepos]
            else:
                code = ""  # no error code specified
            return (
                loc
                + self.style("error:", "red", bold=True)
                + self.highlight_quote_groups(msg)
                + self.style(code, "yellow")
            )
        elif ": note:" in error:
            loc, msg = error.split("note:", maxsplit=1)
            formatted = self.highlight_quote_groups(self.underline_link(msg))
            return loc + self.style("note:", "blue") + formatted
        elif error.startswith(" " * DEFAULT_SOURCE_OFFSET):
            # TODO: detecting source code highlights through an indent can be surprising.
            if "^" not in error:
                return self.style(error, "none", dim=True)
            return self.style(error, "red")
        else:
            return error

    def highlight_quote_groups(self, msg: str) -> str:
        """Make groups quoted with double quotes bold (including quotes).

        This is used to highlight types, attribute names etc.
        """
        if msg.count('"') % 2:
            # Broken error message, don't do any formatting.
            return msg
        parts = msg.split('"')
        out = ""
        for i, part in enumerate(parts):
            if i % 2 == 0:
                out += self.style(part, "none")
            else:
                out += self.style('"' + part + '"', "none", bold=True)
        return out

    def underline_link(self, note: str) -> str:
        """Underline a link in a note message (if any).

        This assumes there is at most one link in the message.
        """
        match = re.search(r"https?://\S*", note)
        if not match:
            return note
        start = match.start()
        end = match.end()
        return note[:start] + self.style(note[start:end], "none", underline=True) + note[end:]

    def format_success(self, n_sources: int, use_color: bool = True) -> str:
        """Format short summary in case of success.

        n_sources is total number of files passed directly on command line,
        i.e. excluding stubs and followed imports.
        """
        msg = f"Success: no issues found in {n_sources} source file{plural_s(n_sources)}"
        if not use_color:
            return msg
        return self.style(msg, "green", bold=True)

    def format_error(
        self,
        n_errors: int,
        n_files: int,
        n_sources: int,
        *,
        blockers: bool = False,
        use_color: bool = True,
    ) -> str:
        """Format a short summary in case of errors."""
        msg = f"Found {n_errors} error{plural_s(n_errors)} in {n_files} file{plural_s(n_files)}"
        if blockers:
            msg += " (errors prevented further checking)"
        else:
            msg += f" (checked {n_sources} source file{plural_s(n_sources)})"
        if not use_color:
            return msg
        return self.style(msg, "red", bold=True)


def is_typeshed_file(typeshed_dir: str | None, file: str) -> bool:
    typeshed_dir = typeshed_dir if typeshed_dir is not None else TYPESHED_DIR
    try:
        return os.path.commonpath((typeshed_dir, os.path.abspath(file))) == typeshed_dir
    except ValueError:  # Different drives on Windows
        return False


def is_stub_package_file(file: str) -> bool:
    # Use hacky heuristics to check whether file is part of a PEP 561 stub package.
    if not file.endswith(".pyi"):
        return False
    return any(component.endswith("-stubs") for component in os.path.split(os.path.abspath(file)))


def unnamed_function(name: str | None) -> bool:
    return name is not None and name == "_"


time_ref = time.perf_counter_ns


def time_spent_us(t0: int) -> int:
    return int((time.perf_counter_ns() - t0) / 1000)


def plural_s(s: int | Sized) -> str:
    count = s if isinstance(s, int) else len(s)
    if count != 1:
        return "s"
    else:
        return ""


def quote_docstring(docstr: str) -> str:
    """Returns docstring correctly encapsulated in a single or double quoted form."""
    # Uses repr to get hint on the correct quotes and escape everything properly.
    # Creating multiline string for prettier output.
    docstr_repr = "\n".join(re.split(r"(?<=[^\\])\\n", repr(docstr)))

    if docstr_repr.startswith("'"):
        # Enforce double quotes when it's safe to do so.
        # That is when double quotes are not in the string
        # or when it doesn't end with a single quote.
        if '"' not in docstr_repr[1:-1] and docstr_repr[-2] != "'":
            return f'"""{docstr_repr[1:-1]}"""'
        return f"''{docstr_repr}''"
    else:
        return f'""{docstr_repr}""'
