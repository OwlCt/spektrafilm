"""Rewrite a conda-packed prefix after Spektrafilm.app is moved.

conda-unpack only replaces the original build prefix. Once that has run, a
later move has to replace the previous absolute prefix in place. Binary files
keep their size by padding with NUL bytes, so the new path must be no longer
than the old one.
"""

from __future__ import annotations

import os
import re
import sys


def binary_replace(data: bytes, old: bytes, new: bytes) -> bytes:
    """Same length-preserving C-string rewrite conda-pack uses."""

    def replace(match: re.Match[bytes]) -> bytes:
        chunk = match.group()
        occurrences = chunk.count(old)
        padding = (len(old) - len(new)) * occurrences
        if padding < 0:
            raise ValueError("new prefix is longer than the old prefix")
        return chunk.replace(old, new) + (b"\0" * padding)

    pattern = re.compile(re.escape(old) + b"([^\0]*?)\0")
    return pattern.sub(replace, data)


def rewrite_file(path: str, old: bytes, new: bytes) -> bool:
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return False
    if old not in data:
        return False
    if b"\0" in data:
        updated = binary_replace(data, old, new)
    else:
        updated = data.replace(old, new)
    if updated == data:
        return False
    with open(path, "wb") as handle:
        handle.write(updated)
    return True


def rewrite_tree(root: str, old: str, new: str) -> int:
    old_b = old.encode("utf-8")
    new_b = new.encode("utf-8")
    if len(new_b) > len(old_b):
        raise SystemExit(
            "spektrafilm: the new app location is longer than the previous one "
            f"({len(new_b)} > {len(old_b)} bytes).\n"
            "Move Spektrafilm.app to a shorter path, for example /Applications, "
            "then launch it again."
        )
    changed = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in list(dirnames):
            link_path = os.path.join(dirpath, name)
            if not os.path.islink(link_path):
                continue
            target = os.readlink(link_path)
            if old in target:
                os.remove(link_path)
                os.symlink(target.replace(old, new), link_path)
                changed += 1
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                target = os.readlink(path)
                if old in target:
                    os.remove(path)
                    os.symlink(target.replace(old, new), path)
                    changed += 1
                continue
            if rewrite_file(path, old_b, new_b):
                changed += 1
    return changed


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} OLD_PREFIX NEW_PREFIX")
    old, new = sys.argv[1], sys.argv[2]
    if old == new:
        return
    count = rewrite_tree(new, old, new)
    print(f"spektrafilm: rewrote {count} paths")


if __name__ == "__main__":
    main()
