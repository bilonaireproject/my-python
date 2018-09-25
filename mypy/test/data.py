"""Utilities for processing .test files containing test case descriptions."""

import os.path
import os
import tempfile
import posixpath
import re
import sys
from os import remove, rmdir
import shutil
from abc import abstractmethod

import pytest  # type: ignore  # no pytest in typeshed
from typing import List, Tuple, Set, Optional, Iterator, Any, Dict, NamedTuple, Union

from mypy.test.config import test_data_prefix, test_temp_dir

root_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))

# File modify/create operation: copy module contents from source_path.
UpdateFile = NamedTuple('UpdateFile', [('module', str),
                                       ('source_path', str),
                                       ('target_path', str)])

# File delete operation: delete module file.
DeleteFile = NamedTuple('DeleteFile', [('module', str),
                                       ('path', str)])

FileOperation = Union[UpdateFile, DeleteFile]


def parse_test_case(suite: 'DataSuite', test_items: List['TestItem'], file: str,
                    case: 'DataDrivenTestCase') -> None:
    """Parse and prepare a single case from suite with test case descriptions.

    This method is part of the setup phase, just before the test case is run.
    """
    base_path = suite.base_path
    if suite.native_sep:
        join = os.path.join
    else:
        join = posixpath.join  # type: ignore

    out_section_missing = suite.required_out_section

    files = []  # type: List[Tuple[str, str]] # path and contents
    output_files = []  # type: List[Tuple[str, str]] # path and contents for output files
    output = []  # type: List[str]  # Regular output errors
    output2 = {}  # type: Dict[int, List[str]]  # Output errors for incremental, runs 2+
    deleted_paths = {}  # type: Dict[int, Set[str]]  # from run number of paths
    stale_modules = {}  # type: Dict[int, Set[str]]  # from run number to module names
    rechecked_modules = {}  # type: Dict[ int, Set[str]]  # from run number module names
    triggered = []  # type: List[str]  # Active triggers (one line per incremental step)

    # Process the parsed items. Each item has a header of form [id args],
    # optionally followed by lines of text.
    item = first_item = test_items[0]
    for item in test_items[1:]:
        if item.id == 'file' or item.id == 'outfile':
            # Record an extra file needed for the test case.
            assert item.arg is not None
            contents = expand_variables('\n'.join(item.data))
            file_entry = (join(base_path, item.arg), contents)
            if item.id == 'file':
                files.append(file_entry)
            else:
                output_files.append(file_entry)
        elif item.id in ('builtins', 'builtins_py2'):
            # Use an alternative stub file for the builtins module.
            assert item.arg is not None
            mpath = join(os.path.dirname(file), item.arg)
            fnam = 'builtins.pyi' if item.id == 'builtins' else '__builtin__.pyi'
            with open(mpath) as f:
                files.append((join(base_path, fnam), f.read()))
        elif item.id == 'typing':
            # Use an alternative stub file for the typing module.
            assert item.arg is not None
            src_path = join(os.path.dirname(file), item.arg)
            with open(src_path) as f:
                files.append((join(base_path, 'typing.pyi'), f.read()))
        elif re.match(r'stale[0-9]*$', item.id):
            passnum = 1 if item.id == 'stale' else int(item.id[len('stale'):])
            assert passnum > 0
            modules = (set() if item.arg is None else {t.strip() for t in item.arg.split(',')})
            stale_modules[passnum] = modules
        elif re.match(r'rechecked[0-9]*$', item.id):
            passnum = 1 if item.id == 'rechecked' else int(item.id[len('rechecked'):])
            assert passnum > 0
            modules = (set() if item.arg is None else {t.strip() for t in item.arg.split(',')})
            rechecked_modules[passnum] = modules
        elif item.id == 'delete':
            # File to delete during a multi-step test case
            assert item.arg is not None
            m = re.match(r'(.*)\.([0-9]+)$', item.arg)
            assert m, 'Invalid delete section: {}'.format(item.arg)
            num = int(m.group(2))
            assert num >= 2, "Can't delete during step {}".format(num)
            full = join(base_path, m.group(1))
            deleted_paths.setdefault(num, set()).add(full)
        elif re.match(r'out[0-9]*$', item.id):
            tmp_output = [expand_variables(line) for line in item.data]
            if os.path.sep == '\\':
                tmp_output = [fix_win_path(line) for line in tmp_output]
            if item.id == 'out' or item.id == 'out1':
                output = tmp_output
            else:
                passnum = int(item.id[len('out'):])
                assert passnum > 1
                output2[passnum] = tmp_output
            out_section_missing = False
        elif item.id == 'triggered' and item.arg is None:
            triggered = item.data
        else:
            raise ValueError(
                'Invalid section header {} in {} at line {}'.format(
                    item.id, file, item.line))

    if out_section_missing:
        raise ValueError(
            '{}, line {}: Required output section not found'.format(
                file, first_item.line))

    for passnum in stale_modules.keys():
        if passnum not in rechecked_modules:
            # If the set of rechecked modules isn't specified, make it the same as the set
            # of modules with a stale public interface.
            rechecked_modules[passnum] = stale_modules[passnum]
        if (passnum in stale_modules
                and passnum in rechecked_modules
                and not stale_modules[passnum].issubset(rechecked_modules[passnum])):
            raise ValueError(
                ('Stale modules after pass {} must be a subset of rechecked '
                 'modules ({}:{})').format(passnum, file, first_item.line))

    input = first_item.data
    expand_errors(input, output, 'main')
    for file_path, contents in files:
        expand_errors(contents.split('\n'), output, file_path)

    case.input = input
    case.output = output
    case.output2 = output2
    case.lastline = item.line
    case.file = file
    case.files = files
    case.output_files = output_files
    case.expected_stale_modules = stale_modules
    case.expected_rechecked_modules = rechecked_modules
    case.deleted_paths = deleted_paths
    case.triggered = triggered or []


class DataDrivenTestCase(pytest.Item):  # type: ignore  # inheriting from Any
    """Holds parsed data-driven test cases, and handles directory setup and teardown."""

    input = None  # type: List[str]
    output = None  # type: List[str]  # Output for the first pass
    output2 = None  # type: Dict[int, List[str]]  # Output for runs 2+, indexed by run number

    file = ''
    line = 0

    # (file path, file content) tuples
    files = None  # type: List[Tuple[str, str]]
    expected_stale_modules = None  # type: Dict[int, Set[str]]
    expected_rechecked_modules = None  # type: Dict[int, Set[str]]

    # Files/directories to clean up after test case; (is directory, path) tuples
    clean_up = None  # type: List[Tuple[bool, str]]

    def __init__(self,
                 parent: 'DataSuiteCollector',
                 suite: 'DataSuite',
                 path: str,
                 name: str,
                 writescache: bool,
                 only_when: str,
                 skip: bool,
                 data: str,
                 line: int) -> None:
        super().__init__(name, parent)
        self.path = path
        self.suite = suite
        self.writescache = writescache
        self.only_when = only_when
        self.skip = skip
        self.data = data
        self.line = line
        self.old_cwd = None  # type: Optional[str]
        self.tmpdir = None  # type: Optional[tempfile.TemporaryDirectory[str]]
        self.clean_up = []

    def runtest(self) -> None:
        if self.skip:
            pytest.skip()
        suite = self.parent.obj()
        suite.setup()
        try:
            suite.run_case(self)
        except Exception:
            # As a debugging aid, support copying the contents of the tmp directory somewhere
            save_dir = self.config.getoption('--save-failures-to', None)  # type: Optional[str]
            if save_dir:
                assert self.tmpdir is not None
                target_dir = os.path.join(save_dir, os.path.basename(self.tmpdir.name))
                print("Copying data from test {} to {}".format(self.name, target_dir))
                if not os.path.isabs(target_dir):
                    assert self.old_cwd
                    target_dir = os.path.join(self.old_cwd, target_dir)
                shutil.copytree(self.tmpdir.name, target_dir)
            raise

    def setup(self) -> None:
        parse_test_case(suite=self.suite,
                        test_items=parse_test_data(self.data, self.name),
                        file=self.path,
                        case=self)
        self.old_cwd = os.getcwd()
        self.tmpdir = tempfile.TemporaryDirectory(prefix='mypy-test-')
        os.chdir(self.tmpdir.name)
        os.mkdir(test_temp_dir)
        encountered_files = set()
        self.clean_up = []
        for paths in self.deleted_paths.values():
            for path in paths:
                self.clean_up.append((False, path))
                encountered_files.add(path)
        for path, content in self.files:
            dir = os.path.dirname(path)
            for d in self.add_dirs(dir):
                self.clean_up.append((True, d))
            with open(path, 'w') as f:
                f.write(content)
            if path not in encountered_files:
                self.clean_up.append((False, path))
                encountered_files.add(path)
            if re.search(r'\.[2-9]$', path):
                # Make sure new files introduced in the second and later runs are accounted for
                renamed_path = path[:-2]
                if renamed_path not in encountered_files:
                    encountered_files.add(renamed_path)
                    self.clean_up.append((False, renamed_path))
        for path, _ in self.output_files:
            # Create directories for expected output and mark them to be cleaned up at the end
            # of the test case.
            dir = os.path.dirname(path)
            for d in self.add_dirs(dir):
                self.clean_up.append((True, d))
            self.clean_up.append((False, path))

    def add_dirs(self, dir: str) -> List[str]:
        """Add all subdirectories required to create dir.

        Return an array of the created directories in the order of creation.
        """
        if dir == '' or os.path.isdir(dir):
            return []
        else:
            dirs = self.add_dirs(os.path.dirname(dir)) + [dir]
            os.mkdir(dir)
            return dirs

    def teardown(self) -> None:
        # First remove files.
        for is_dir, path in reversed(self.clean_up):
            if not is_dir:
                try:
                    remove(path)
                except FileNotFoundError:
                    # Breaking early using Ctrl+C may happen before file creation. Also, some
                    # files may be deleted by a test case.
                    pass
        # Then remove directories.
        for is_dir, path in reversed(self.clean_up):
            if is_dir:
                pycache = os.path.join(path, '__pycache__')
                if os.path.isdir(pycache):
                    shutil.rmtree(pycache)
                # As a somewhat nasty hack, ignore any dirs with .mypy_cache in the path,
                # to allow test cases to intentionally corrupt the cache without provoking
                # the test suite when there are still files left over.
                # (Looking at / should be fine on windows because these are paths specified
                # in the test cases.)
                if '/.mypy_cache' in path:
                    continue
                try:
                    rmdir(path)
                except OSError as error:
                    print(' ** Error removing directory %s -- contents:' % path)
                    for item in os.listdir(path):
                        print('  ', item)
                    # Most likely, there are some files in the
                    # directory. Use rmtree to nuke the directory, but
                    # fail the test case anyway, since this seems like
                    # a bug in a test case -- we shouldn't leave
                    # garbage lying around. By nuking the directory,
                    # the next test run hopefully passes.
                    path = error.filename
                    # Be defensive -- only call rmtree if we're sure we aren't removing anything
                    # valuable.
                    if path.startswith(test_temp_dir + '/') and os.path.isdir(path):
                        shutil.rmtree(path)
                    raise
        assert self.old_cwd is not None and self.tmpdir is not None, \
            "test was not properly set up"
        os.chdir(self.old_cwd)
        try:
            self.tmpdir.cleanup()
        except OSError:
            pass
        self.old_cwd = None
        self.tmpdir = None

    def reportinfo(self) -> Tuple[str, int, str]:
        return self.file, self.line, self.name

    def repr_failure(self, excinfo: Any) -> str:
        if excinfo.errisinstance(SystemExit):
            # We assume that before doing exit() (which raises SystemExit) we've printed
            # enough context about what happened so that a stack trace is not useful.
            # In particular, uncaught exceptions during semantic analysis or type checking
            # call exit() and they already print out a stack trace.
            excrepr = excinfo.exconly()
        else:
            self.parent._prunetraceback(excinfo)
            excrepr = excinfo.getrepr(style='short')

        return "data: {}:{}:\n{}".format(self.file, self.line, excrepr)

    def find_steps(self) -> List[List[FileOperation]]:
        """Return a list of descriptions of file operations for each incremental step.

        The first list item corresponds to the first incremental step, the second for the
        second step, etc. Each operation can either be a file modification/creation (UpdateFile)
        or deletion (DeleteFile).

        Defaults to having two steps if there aern't any operations.
        """
        steps = {}  # type: Dict[int, List[FileOperation]]
        for path, _ in self.files:
            m = re.match(r'.*\.([0-9]+)$', path)
            if m:
                num = int(m.group(1))
                assert num >= 2
                target_path = re.sub(r'\.[0-9]+$', '', path)
                module = module_from_path(target_path)
                operation = UpdateFile(module, path, target_path)
                steps.setdefault(num, []).append(operation)
        for num, paths in self.deleted_paths.items():
            assert num >= 2
            for path in paths:
                module = module_from_path(path)
                steps.setdefault(num, []).append(DeleteFile(module, path))
        max_step = max(steps) if steps else 2
        return [steps.get(num, []) for num in range(2, max_step + 1)]


def module_from_path(path: str) -> str:
    path = re.sub(r'\.pyi?$', '', path)
    # We can have a mix of Unix-style and Windows-style separators.
    parts = re.split(r'[/\\]', path)
    assert parts[0] == test_temp_dir
    del parts[0]
    module = '.'.join(parts)
    module = re.sub(r'\.__init__$', '', module)
    return module


class TestItem:
    """Parsed test caseitem.

    An item is of the form
      [id arg]
      .. data ..
    """

    id = ''
    arg = ''  # type: Optional[str]

    # Text data, array of 8-bit strings
    data = None  # type: List[str]

    file = ''
    line = 0  # Line number in file

    def __init__(self, id: str, arg: Optional[str], data: List[str],
                 line: int) -> None:
        self.id = id
        self.arg = arg
        self.data = data
        self.line = line


def parse_test_data(raw_data: str, name: str) -> List[TestItem]:
    """Parse a list of lines that represent a sequence of test items."""

    lines = ['', '[case ' + name + ']'] + raw_data.split('\n')
    ret = []  # type: List[TestItem]
    data = []  # type: List[str]

    id = None  # type: Optional[str]
    arg = None  # type: Optional[str]

    i = 0
    i0 = 0
    while i < len(lines):
        s = lines[i].strip()

        if lines[i].startswith('[') and s.endswith(']') and not s.startswith('[['):
            if id:
                data = collapse_line_continuation(data)
                data = strip_list(data)
                ret.append(TestItem(id, arg, strip_list(data), i0 + 1))

            i0 = i
            id = s[1:-1]
            arg = None
            if ' ' in id:
                arg = id[id.index(' ') + 1:]
                id = id[:id.index(' ')]
            data = []
        elif lines[i].startswith('[['):
            data.append(lines[i][1:])
        elif not lines[i].startswith('--'):
            data.append(lines[i])
        elif lines[i].startswith('----'):
            data.append(lines[i][2:])
        i += 1

    # Process the last item.
    if id:
        data = collapse_line_continuation(data)
        data = strip_list(data)
        ret.append(TestItem(id, arg, data, i0 + 1))

    return ret


def strip_list(l: List[str]) -> List[str]:
    """Return a stripped copy of l.

    Strip whitespace at the end of all lines, and strip all empty
    lines from the end of the array.
    """

    r = []  # type: List[str]
    for s in l:
        # Strip spaces at end of line
        r.append(re.sub(r'\s+$', '', s))

    while len(r) > 0 and r[-1] == '':
        r.pop()

    return r


def collapse_line_continuation(l: List[str]) -> List[str]:
    r = []  # type: List[str]
    cont = False
    for s in l:
        ss = re.sub(r'\\$', '', s)
        if cont:
            r[-1] += re.sub('^ +', '', ss)
        else:
            r.append(ss)
        cont = s.endswith('\\')
    return r


def expand_variables(s: str) -> str:
    return s.replace('<ROOT>', root_dir)


def expand_errors(input: List[str], output: List[str], fnam: str) -> None:
    """Transform comments such as '# E: message' or
    '# E:3: message' in input.

    The result is lines like 'fnam:line: error: message'.
    """

    for i in range(len(input)):
        # The first in the split things isn't a comment
        for possible_err_comment in input[i].split(' # ')[1:]:
            m = re.search(
                '^([ENW]):((?P<col>\d+):)? (?P<message>.*)$',
                possible_err_comment.strip())
            if m:
                if m.group(1) == 'E':
                    severity = 'error'
                elif m.group(1) == 'N':
                    severity = 'note'
                elif m.group(1) == 'W':
                    severity = 'warning'
                col = m.group('col')
                if col is None:
                    output.append(
                        '{}:{}: {}: {}'.format(fnam, i + 1, severity, m.group('message')))
                else:
                    output.append('{}:{}:{}: {}: {}'.format(
                        fnam, i + 1, col, severity, m.group('message')))


def fix_win_path(line: str) -> str:
    r"""Changes Windows paths to Linux paths in error messages.

    E.g. foo\bar.py -> foo/bar.py.
    """
    line = line.replace(root_dir, root_dir.replace('\\', '/'))
    m = re.match(r'^([\S/]+):(\d+:)?(\s+.*)', line)
    if not m:
        return line
    else:
        filename, lineno, message = m.groups()
        return '{}:{}{}'.format(filename.replace('\\', '/'),
                                lineno or '', message)


def fix_cobertura_filename(line: str) -> str:
    r"""Changes filename paths to Linux paths in Cobertura output files.

    E.g. filename="pkg\subpkg\a.py" -> filename="pkg/subpkg/a.py".
    """
    m = re.search(r'<class .* filename="(?P<filename>.*?)"', line)
    if not m:
        return line
    return '{}{}{}'.format(line[:m.start(1)],
                           m.group('filename').replace('\\', '/'),
                           line[m.end(1):])


##
#
# pytest setup
#
##


# This function name is special to pytest.  See
# https://docs.pytest.org/en/latest/reference.html#initialization-hooks
def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup('mypy')
    group.addoption('--update-data', action='store_true', default=False,
                    help='Update test data to reflect actual output'
                         ' (supported only for certain tests)')
    group.addoption('--save-failures-to', default=None,
                    help='Copy the temp directories from failing tests to a target directory')
    group.addoption('--mypy-verbose', action='count',
                    help='Set the verbose flag when creating mypy Options')


# This function name is special to pytest.  See
# http://doc.pytest.org/en/latest/writing_plugins.html#collection-hooks
def pytest_pycollect_makeitem(collector: Any, name: str,
                              obj: object) -> 'Optional[Any]':
    """Called by pytest on each object in modules configured in conftest.py files.

    collector is pytest.Collector, returns Optional[pytest.Class]
    """
    if isinstance(obj, type):
        # Only classes derived from DataSuite contain test cases, not the DataSuite class itself
        if issubclass(obj, DataSuite) and obj is not DataSuite:
            # Non-None result means this obj is a test case.
            # The collect method of the returned DataSuiteCollector instance will be called later,
            # with self.obj being obj.
            return DataSuiteCollector(name, parent=collector)
    return None


def split_test_cases(parent: 'DataSuiteCollector', suite: 'DataSuite',
                     path: str) -> Iterator['DataDrivenTestCase']:
    """Iterate over raw test cases in file, at collection time, ignoring sub items.

    The collection phase is slow, so any heavy processing should be deferred to after
    uninteresting tests are filtered (when using -k PATTERN switch).
    """
    with open(path, encoding='utf-8') as f:
        data = f.read()
    cases = re.split('^\[case ([a-zA-Z_0-9]+)'
                     '(-writescache)?'
                     '(-only_when_cache|-only_when_nocache)?'
                     '(-skip)?'
                     '\][ \t]*$\n', data,
                     flags=re.DOTALL | re.MULTILINE)
    line_no = cases[0].count('\n') + 1
    for i in range(1, len(cases), 5):
        name, writescache, only_when, skip, data = cases[i:i + 5]
        yield DataDrivenTestCase(parent, suite, path,
                                 name=add_test_name_suffix(name, suite.test_name_suffix),
                                 writescache=bool(writescache),
                                 only_when=only_when,
                                 skip=bool(skip),
                                 data=data,
                                 line=line_no)
        line_no += data.count('\n') + 1


class DataSuiteCollector(pytest.Class):  # type: ignore  # inheriting from Any
    def collect(self) -> Iterator[pytest.Item]:  # type: ignore
        """Called by pytest on each of the object returned from pytest_pycollect_makeitem"""

        # obj is the object for which pytest_pycollect_makeitem returned self.
        suite = self.obj  # type: DataSuite
        for f in suite.files:
            yield from split_test_cases(self, suite, os.path.join(suite.data_prefix, f))


def add_test_name_suffix(name: str, suffix: str) -> str:
    # Find magic suffix of form "-foobar" (used for things like "-skip").
    m = re.search(r'-[-A-Za-z0-9]+$', name)
    if m:
        # Insert suite-specific test name suffix before the magic suffix
        # which must be the last thing in the test case name since we
        # are using endswith() checks.
        magic_suffix = m.group(0)
        return name[:-len(magic_suffix)] + suffix + magic_suffix
    else:
        return name + suffix


def is_incremental(testcase: DataDrivenTestCase) -> bool:
    return 'incremental' in testcase.name.lower() or 'incremental' in testcase.file


def has_stable_flags(testcase: DataDrivenTestCase) -> bool:
    if any(re.match(r'# flags[2-9]:', line) for line in testcase.input):
        return False
    for filename, contents in testcase.files:
        if os.path.basename(filename).startswith('mypy.ini.'):
            return False
    return True


class DataSuite:
    # option fields - class variables
    files = None  # type: List[str]

    base_path = test_temp_dir

    # Allow external users of the test code to override the data prefix
    data_prefix = test_data_prefix

    required_out_section = False

    native_sep = False

    # Name suffix automatically added to each test case in the suite (can be
    # used to distinguish test cases in suites that share data files)
    test_name_suffix = ''

    def setup(self) -> None:
        """Setup fixtures (ad-hoc)"""
        pass

    @abstractmethod
    def run_case(self, testcase: DataDrivenTestCase) -> None:
        raise NotImplementedError
