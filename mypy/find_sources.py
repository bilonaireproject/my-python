"""Routines for finding the sources that mypy will check"""

import os.path

from typing import List, Sequence, Set, Tuple, Optional, Dict

from mypy.build import BuildSource, PYTHON_EXTENSIONS
from mypy.fscache import FileSystemMetaCache
from mypy.options import Options


PY_EXTENSIONS = tuple(PYTHON_EXTENSIONS)


class InvalidSourceList(Exception):
    """Exception indicating a problem in the list of sources given to mypy."""


def create_source_list(files: Sequence[str], options: Options,
                       fscache: Optional[FileSystemMetaCache] = None,
                       allow_empty_dir: bool = False) -> List[BuildSource]:
    """From a list of source files/directories, makes a list of BuildSources.

    Raises InvalidSourceList on errors.
    """
    fscache = fscache or FileSystemMetaCache()
    finder = SourceFinder(fscache)

    targets = []
    for f in files:
        if f.endswith(PY_EXTENSIONS):
            # Can raise InvalidSourceList if a directory doesn't have a valid module name.
            targets.append(BuildSource(f, finder.crawl_up(f), None))
        elif fscache.isdir(f):
            sub_targets = finder.expand_dir(f)
            if not sub_targets and not allow_empty_dir:
                raise InvalidSourceList("There are no .py[i] files in directory '{}'"
                                        .format(f))
            targets.extend(sub_targets)
        else:
            mod = os.path.basename(f) if options.scripts_are_modules else None
            targets.append(BuildSource(f, mod, None))
    return targets


def keyfunc(name: str) -> Tuple[int, str]:
    """Determines sort order for directory listing.

    The desirable property is foo < foo.pyi < foo.py.
    """
    base, suffix = os.path.splitext(name)
    for i, ext in enumerate(PY_EXTENSIONS):
        if suffix == ext:
            return (i, base)
    return (-1, name)


class SourceFinder:
    def __init__(self, fscache: FileSystemMetaCache) -> None:
        self.fscache = fscache
        # A cache for package names, mapping from module id to directory path
        self.package_cache = {}  # type: Dict[str, str]

    def expand_dir(self, arg: str, mod_prefix: str = '') -> List[BuildSource]:
        """Convert a directory name to a list of sources to build."""
        f = self.get_init_file(arg)
        if mod_prefix and not f:
            return []
        seen = set()  # type: Set[str]
        sources = []
        if f and not mod_prefix:
            top_mod = self.crawl_up(f)
            mod_prefix = top_mod + '.'
        if mod_prefix:
            sources.append(BuildSource(f, mod_prefix.rstrip('.'), None))
        names = self.fscache.listdir(arg)
        names.sort(key=keyfunc)
        for name in names:
            path = os.path.join(arg, name)
            if self.fscache.isdir(path):
                sub_sources = self.expand_dir(path, mod_prefix + name + '.')
                if sub_sources:
                    seen.add(name)
                    sources.extend(sub_sources)
            else:
                base, suffix = os.path.splitext(name)
                if base == '__init__':
                    continue
                if base not in seen and '.' not in base and suffix in PY_EXTENSIONS:
                    seen.add(base)
                    src = BuildSource(path, mod_prefix + base, None)
                    sources.append(src)
        return sources

    def crawl_up(self, arg: str) -> str:
        """Given a .py[i] filename, return module.

        We crawl up the path until we find a directory without
        __init__.py[i], or until we run out of path components.
        """
        dir, mod = os.path.split(arg)
        mod = strip_py(mod) or mod
        base = self.crawl_up_dir(dir)
        if mod == '__init__' or not mod:
            mod = base
        else:
            mod = module_join(base, mod)

        return mod

    def crawl_up_dir(self, dir: str) -> str:
        """Given a directory name, return the corresponding module name.

        Use package_cache to cache results.
        """
        if dir in self.package_cache:
            return self.package_cache[dir]

        parent_dir, base = os.path.split(dir)
        if not dir or not self.get_init_file(dir) or not base:
            res = ''
        else:
            # Ensure that base is a valid python module name
            if not base.isidentifier():
                raise InvalidSourceList('{} is not a valid Python package name'.format(base))
            parent = self.crawl_up_dir(parent_dir)
            res = module_join(parent, base)

        self.package_cache[dir] = res
        return res

    def get_init_file(self, dir: str) -> Optional[str]:
        """Check whether a directory contains a file named __init__.py[i].

        If so, return the file's name (with dir prefixed).  If not, return
        None.

        This prefers .pyi over .py (because of the ordering of PY_EXTENSIONS).
        """
        for ext in PY_EXTENSIONS:
            f = os.path.join(dir, '__init__' + ext)
            if self.fscache.isfile(f):
                return f
        return None


def module_join(parent: str, child: str) -> str:
    """Join module ids, accounting for a possibly empty parent."""
    if parent:
        return parent + '.' + child
    else:
        return child


def strip_py(arg: str) -> Optional[str]:
    """Strip a trailing .py or .pyi suffix.

    Return None if no such suffix is found.
    """
    for ext in PY_EXTENSIONS:
        if arg.endswith(ext):
            return arg[:-len(ext)]
    return None
