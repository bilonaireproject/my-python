import sys

if sys.platform == "win32":
    from distutils.cmd import Command
    class bdist_msi(Command):
        def initialize_options(self) -> None: ...
        def finalize_options(self) -> None: ...
        def run(self) -> None: ...
