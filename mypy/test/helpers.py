import os
import re
import sys
import time

from typing import List, Dict, Tuple, Callable, Any, Optional

from mypy import defaults

import pytest  # type: ignore  # no pytest in typeshed
from unittest import TestCase as Suite

from mypy.main import process_options
from mypy.options import Options
from mypy.test.data import DataDrivenTestCase

skip = pytest.mark.skip

# AssertStringArraysEqual displays special line alignment helper messages if
# the first different line has at least this many characters,
MIN_LINE_LENGTH_FOR_ALIGNMENT = 5


def assert_string_arrays_equal(expected: List[str], actual: List[str],
                               msg: str) -> None:
    """Assert that two string arrays are equal.

    Display any differences in a human-readable form.
    """

    actual = clean_up(actual)

    if actual != expected:
        num_skip_start = num_skipped_prefix_lines(expected, actual)
        num_skip_end = num_skipped_suffix_lines(expected, actual)

        sys.stderr.write('Expected:\n')

        # If omit some lines at the beginning, indicate it by displaying a line
        # with '...'.
        if num_skip_start > 0:
            sys.stderr.write('  ...\n')

        # Keep track of the first different line.
        first_diff = -1

        # Display only this many first characters of identical lines.
        width = 75

        for i in range(num_skip_start, len(expected) - num_skip_end):
            if i >= len(actual) or expected[i] != actual[i]:
                if first_diff < 0:
                    first_diff = i
                sys.stderr.write('  {:<45} (diff)'.format(expected[i]))
            else:
                e = expected[i]
                sys.stderr.write('  ' + e[:width])
                if len(e) > width:
                    sys.stderr.write('...')
            sys.stderr.write('\n')
        if num_skip_end > 0:
            sys.stderr.write('  ...\n')

        sys.stderr.write('Actual:\n')

        if num_skip_start > 0:
            sys.stderr.write('  ...\n')

        for j in range(num_skip_start, len(actual) - num_skip_end):
            if j >= len(expected) or expected[j] != actual[j]:
                sys.stderr.write('  {:<45} (diff)'.format(actual[j]))
            else:
                a = actual[j]
                sys.stderr.write('  ' + a[:width])
                if len(a) > width:
                    sys.stderr.write('...')
            sys.stderr.write('\n')
        if actual == []:
            sys.stderr.write('  (empty)\n')
        if num_skip_end > 0:
            sys.stderr.write('  ...\n')

        sys.stderr.write('\n')

        if first_diff >= 0 and first_diff < len(actual) and (
                len(expected[first_diff]) >= MIN_LINE_LENGTH_FOR_ALIGNMENT
                or len(actual[first_diff]) >= MIN_LINE_LENGTH_FOR_ALIGNMENT):
            # Display message that helps visualize the differences between two
            # long lines.
            show_align_message(expected[first_diff], actual[first_diff])

        raise AssertionFailure(msg)


def update_testcase_output(testcase: DataDrivenTestCase, output: List[str]) -> None:
    assert testcase.old_cwd is not None, "test was not properly set up"
    testcase_path = os.path.join(testcase.old_cwd, testcase.file)
    with open(testcase_path) as f:
        data_lines = f.read().splitlines()
    test = '\n'.join(data_lines[testcase.line:testcase.lastline])

    mapping = {}  # type: Dict[str, List[str]]
    for old, new in zip(testcase.output, output):
        PREFIX = 'error:'
        ind = old.find(PREFIX)
        if ind != -1 and old[:ind] == new[:ind]:
            old, new = old[ind + len(PREFIX):], new[ind + len(PREFIX):]
        mapping.setdefault(old, []).append(new)

    for old in mapping:
        if test.count(old) == len(mapping[old]):
            betweens = test.split(old)

            # Interleave betweens and mapping[old]
            from itertools import chain
            interleaved = [betweens[0]] + \
                list(chain.from_iterable(zip(mapping[old], betweens[1:])))
            test = ''.join(interleaved)

    data_lines[testcase.line:testcase.lastline] = [test]
    data = '\n'.join(data_lines)
    with open(testcase_path, 'w') as f:
        print(data, file=f)


def show_align_message(s1: str, s2: str) -> None:
    """Align s1 and s2 so that the their first difference is highlighted.

    For example, if s1 is 'foobar' and s2 is 'fobar', display the
    following lines:

      E: foobar
      A: fobar
           ^

    If s1 and s2 are long, only display a fragment of the strings around the
    first difference. If s1 is very short, do nothing.
    """

    # Seeing what went wrong is trivial even without alignment if the expected
    # string is very short. In this case do nothing to simplify output.
    if len(s1) < 4:
        return

    maxw = 72  # Maximum number of characters shown

    sys.stderr.write('Alignment of first line difference:\n')

    trunc = False
    while s1[:30] == s2[:30]:
        s1 = s1[10:]
        s2 = s2[10:]
        trunc = True

    if trunc:
        s1 = '...' + s1
        s2 = '...' + s2

    max_len = max(len(s1), len(s2))
    extra = ''
    if max_len > maxw:
        extra = '...'

    # Write a chunk of both lines, aligned.
    sys.stderr.write('  E: {}{}\n'.format(s1[:maxw], extra))
    sys.stderr.write('  A: {}{}\n'.format(s2[:maxw], extra))
    # Write an indicator character under the different columns.
    sys.stderr.write('     ')
    for j in range(min(maxw, max(len(s1), len(s2)))):
        if s1[j:j + 1] != s2[j:j + 1]:
            sys.stderr.write('^')  # Difference
            break
        else:
            sys.stderr.write(' ')  # Equal
    sys.stderr.write('\n')


def clean_up(a: List[str]) -> List[str]:
    """Remove common directory prefix from all strings in a.

    This uses a naive string replace; it seems to work well enough. Also
    remove trailing carriage returns.
    """
    res = []
    for s in a:
        prefix = os.sep
        ss = s
        for p in prefix, prefix.replace(os.sep, '/'):
            if p != '/' and p != '//' and p != '\\' and p != '\\\\':
                ss = ss.replace(p, '')
        # Ignore spaces at end of line.
        ss = re.sub(' +$', '', ss)
        res.append(re.sub('\\r$', '', ss))
    return res


def num_skipped_prefix_lines(a1: List[str], a2: List[str]) -> int:
    num_eq = 0
    while num_eq < min(len(a1), len(a2)) and a1[num_eq] == a2[num_eq]:
        num_eq += 1
    return max(0, num_eq - 4)


def num_skipped_suffix_lines(a1: List[str], a2: List[str]) -> int:
    num_eq = 0
    while (num_eq < min(len(a1), len(a2))
           and a1[-num_eq - 1] == a2[-num_eq - 1]):
        num_eq += 1
    return max(0, num_eq - 4)


def testfile_pyversion(path: str) -> Tuple[int, int]:
    if path.endswith('python2.test'):
        return defaults.PYTHON2_VERSION
    else:
        return defaults.PYTHON3_VERSION


def testcase_pyversion(path: str, testcase_name: str) -> Tuple[int, int]:
    if testcase_name.endswith('python2'):
        return defaults.PYTHON2_VERSION
    else:
        return testfile_pyversion(path)


def normalize_error_messages(messages: List[str]) -> List[str]:
    """Translate an array of error messages to use / as path separator."""

    a = []
    for m in messages:
        a.append(m.replace(os.sep, '/'))
    return a


def retry_on_error(func: Callable[[], Any], max_wait: float = 1.0) -> None:
    """Retry callback with exponential backoff when it raises OSError.

    If the function still generates an error after max_wait seconds, propagate
    the exception.

    This can be effective against random file system operation failures on
    Windows.
    """
    t0 = time.time()
    wait_time = 0.01
    while True:
        try:
            func()
            return
        except OSError:
            wait_time = min(wait_time * 2, t0 + max_wait - time.time())
            if wait_time <= 0.01:
                # Done enough waiting, the error seems persistent.
                raise
            time.sleep(wait_time)


class AssertionFailure(Exception):
    """Exception used to signal failed test cases."""
    def __init__(self, s: Optional[str] = None) -> None:
        if s:
            super().__init__(s)
        else:
            super().__init__()


def assert_true(b: bool, msg: Optional[str] = None) -> None:
    if not b:
        raise AssertionFailure(msg)


def assert_false(b: bool, msg: Optional[str] = None) -> None:
    if b:
        raise AssertionFailure(msg)


def good_repr(obj: object) -> str:
    if isinstance(obj, str):
        if obj.count('\n') > 1:
            bits = ["'''\\"]
            for line in obj.split('\n'):
                # force repr to use ' not ", then cut it off
                bits.append(repr('"' + line)[2:-1])
            bits[-1] += "'''"
            return '\n'.join(bits)
    return repr(obj)


def assert_equal(a: object, b: object, fmt: str = '{} != {}') -> None:
    if a != b:
        raise AssertionFailure(fmt.format(good_repr(a), good_repr(b)))


def typename(t: type) -> str:
    if '.' in str(t):
        return str(t).split('.')[-1].rstrip("'>")
    else:
        return str(t)[8:-2]


def assert_type(typ: type, value: object) -> None:
    if type(value) != typ:
        raise AssertionFailure('Invalid type {}, expected {}'.format(
            typename(type(value)), typename(typ)))

def parse_options(program_text: str, testcase: DataDrivenTestCase,
                  incremental_step: int) -> Options:
    """Parse comments like '# flags: --foo' in a test case."""
    options = Options()
    flags = re.search('# flags: (.*)$', program_text, flags=re.MULTILINE)
    if incremental_step > 1:
        flags2 = re.search('# flags{}: (.*)$'.format(incremental_step), program_text,
                           flags=re.MULTILINE)
        if flags2:
            flags = flags2

    flag_list = None
    if flags:
        flag_list = flags.group(1).split()
        targets, options = process_options(flag_list, require_targets=False)
        if targets:
            # TODO: support specifying targets via the flags pragma
            raise RuntimeError('Specifying targets via the flags pragma is not supported.')
    else:
        options = Options()

    # Allow custom python version to override testcase_pyversion
    if (not flag_list or
            all(flag not in flag_list for flag in ['--python-version', '-2', '--py2'])):
        options.python_version = testcase_pyversion(testcase.file, testcase.name)

    return options
