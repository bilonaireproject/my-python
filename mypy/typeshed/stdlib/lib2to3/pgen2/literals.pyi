from typing import Dict, Match

simple_escapes: Dict[str, str]

def escape(m: Match[str]) -> str: ...
def evalString(s: str) -> str: ...
def test() -> None: ...
