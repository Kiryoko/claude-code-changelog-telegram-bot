from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import List


VERSION_HEADER_RE = re.compile(r"^##\s+(?P<version>\d+\.\d+\.\d+)\s*$")


@dataclass
class ChangelogEntry:
    version: str
    body: str

    @property
    def content_hash(self) -> str:
        h = hashlib.sha256()
        h.update(self.version.encode())
        h.update(b"\n\n")
        # Normalize line endings and strip trailing whitespace
        normalized = "\n".join(line.rstrip() for line in self.body.splitlines())
        h.update(normalized.encode())
        return h.hexdigest()


def parse_changelog(markdown: str) -> List[ChangelogEntry]:
    lines = markdown.splitlines()
    entries: List[ChangelogEntry] = []
    i = 0
    # Skip optional title line
    while i < len(lines) and not lines[i].startswith("## "):
        i += 1

    current_version: str | None = None
    current_body: list[str] = []

    def flush():
        nonlocal current_version, current_body
        if current_version is not None:
            body_text = "\n".join(current_body).strip().strip("\n")
            entries.append(ChangelogEntry(version=current_version, body=body_text))
        current_version = None
        current_body = []

    while i < len(lines):
        line = lines[i]
        m = VERSION_HEADER_RE.match(line)
        if m:
            # New version header
            flush()
            current_version = m.group("version").strip()
            current_body = []
        else:
            if current_version is not None:
                current_body.append(line)
        i += 1

    # Final flush
    flush()

    return entries

