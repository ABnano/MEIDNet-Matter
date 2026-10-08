"""Every command printed on the Method page runs as printed: each module exists in the installed engine and accepts
every flag the page shows (a first external test found three commands that did not)."""
import re
import subprocess
import sys

import pytest

from pathlib import Path

from tests.conftest import ROOT

METHOD = Path(ROOT) / "frontend" / "src" / "pages" / "Method.tsx"


def printed_commands():
    text = METHOD.read_text(encoding="utf-8")
    block = text[text.index("const RUN_STEPS"):text.index("];", text.index("const RUN_STEPS"))]
    cmds = []
    for raw in re.findall(r"'((?:[^'\\]|\\.)*)'", block):
        for line in raw.replace("\\\\\\n", " ").replace("\\n", "\n").splitlines():
            line = line.strip()
            if line.startswith("python -m meidnet_eval.") or line.startswith("meidnet "):
                for part in re.split(r"\s*&&\s*", line):
                    cmds.append(part.strip())
    return cmds


def help_text(cmd: str) -> str:
    words = cmd.split()
    if words[0] == "python":
        argv = [sys.executable, "-m", words[2], "--help"]
    else:                                          # meidnet <sub>
        argv = [sys.executable, "-m", "meidnet.cli", words[1], "--help"]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    return r.stdout + r.stderr


@pytest.mark.parametrize("cmd", printed_commands())
def test_each_method_command_accepts_its_flags(cmd):
    pytest.importorskip("meidnet_eval")
    flags = {w for w in cmd.split() if w.startswith("--") and not w.startswith("--extra-index")}
    text = help_text(cmd)
    assert "usage:" in text.lower(), f"{cmd.split()[:3]} printed no usage:\n{text[-600:]}"
    missing = [f for f in flags if f not in text]
    assert not missing, f"flags the page prints but the command does not know: {missing}\n{cmd}"


def test_the_page_prints_at_least_nine_commands():
    assert len(printed_commands()) >= 9
