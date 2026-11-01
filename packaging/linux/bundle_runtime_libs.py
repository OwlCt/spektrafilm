"""Copy Qt/xcb/EGL libraries into the PyInstaller tree and point plugins at them.

Qt loads libqxcb.so with dlopen. Those libraries are not linked into the
bootloader, so a clean Debian install otherwise stops on libEGL.so.1 or
libxcb-cursor.so.0. The platform plugins already look in PySide6/Qt/lib via
$ORIGIN; this puts the missing sonames there.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


SKIP_SONAMES = {
    "libc.so.6",
    "libm.so.6",
    "libdl.so.2",
    "libpthread.so.0",
    "librt.so.1",
    "libresolv.so.2",
    "libutil.so.1",
    "ld-linux-x86-64.so.2",
    "linux-vdso.so.1",
}
REQUIRED = (
    "libEGL.so.1",
    "libGL.so.1",
    "libxcb-cursor.so.0",
    "libxcb-icccm.so.4",
    "libxcb-keysyms.so.1",
    "libxcb-xkb.so.1",
    "libxkbcommon.so.0",
    "libxkbcommon-x11.so.0",
)


def _ldconfig() -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    completed = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, check=False)
    for line in completed.stdout.splitlines():
        if "=>" not in line:
            continue
        left, right = line.split("=>", 1)
        soname = left.strip().split()[0]
        mapping.setdefault(soname, Path(right.strip()))
    return mapping


def _ldd(path: Path) -> list[tuple[str, Path | None]]:
    completed = subprocess.run(["ldd", str(path)], capture_output=True, text=True, check=False)
    found: list[tuple[str, Path | None]] = []
    for line in completed.stdout.splitlines():
        if "=>" not in line:
            continue
        left, right = line.split("=>", 1)
        soname = left.strip().split()[0]
        right = right.strip()
        if right.startswith("not found"):
            found.append((soname, None))
            continue
        location = right.split()[0]
        if location.startswith("/"):
            found.append((soname, Path(location)))
    return found


def _copy_soname(resolved: Path, dest_dir: Path, soname: str) -> None:
    real = resolved.resolve()
    target = dest_dir / real.name
    if not target.exists():
        shutil.copy2(real, target, follow_symlinks=True)
    alias = dest_dir / soname
    if alias != target and not alias.exists():
        alias.symlink_to(target.name)


def _rpath(path: Path) -> str:
    completed = subprocess.run(["patchelf", "--print-rpath", str(path)], capture_output=True, text=True, check=False)
    return completed.stdout.strip()


def _ensure_rpath(plugin: Path, qt_lib: Path) -> None:
    relative = Path(os.path.relpath(qt_lib, plugin.parent))
    needed = "$ORIGIN" if relative == Path(".") else f"$ORIGIN/{relative.as_posix()}"
    current = [part for part in _rpath(plugin).split(":") if part]
    for item in (needed, "$ORIGIN"):
        if item not in current:
            current.append(item)
    subprocess.run(["patchelf", "--set-rpath", ":".join(current), str(plugin)], check=True)


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    cores = list(root.rglob("libQt6Core.so*"))
    if not cores:
        raise SystemExit(f"libQt6Core not found under {root}")
    qt_lib = cores[0].parent
    cache = _ldconfig()
    bundled_names = {path.name for path in root.rglob("*") if path.is_file() or path.is_symlink()}
    seeds = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and (
            path.name.startswith(("libqxcb.so", "libqoffscreen.so", "libqeglfs.so", "libQt6Gui.so", "libQt6Widgets.so", "libQt6OpenGL.so"))
            or path.name in {"Spektrafilm", "Spektrafilm.exe"}
        )
    ]
    queue = list(seeds)
    seen: set[Path] = set()
    copied: list[str] = []
    while queue:
        current = queue.pop()
        if current in seen or not current.exists():
            continue
        seen.add(current)
        for soname, resolved in _ldd(current):
            if soname in SKIP_SONAMES or soname.startswith("ld-linux"):
                continue
            if resolved is not None and root in resolved.resolve().parents:
                continue
            if soname.startswith("libQt") and (soname in bundled_names or any(name.startswith(soname + ".") for name in bundled_names)):
                continue
            if resolved is None:
                resolved = cache.get(soname)
            if resolved is None or not resolved.exists():
                continue
            _copy_soname(resolved, qt_lib, soname)
            copied.append(soname)
            queue.append(qt_lib / soname)

    plugins = [
        path
        for path in root.rglob("*.so")
        if path.parent.name in {"platforms", "xcbglintegrations", "egldeviceintegrations", "imageformats"}
    ]
    for plugin in plugins:
        _ensure_rpath(plugin, qt_lib)

    for plugin_dir in {path.parent for path in root.rglob("libqxcb.so")}:
        for soname in REQUIRED:
            source = qt_lib / soname
            if not source.exists():
                continue
            real = source.resolve()
            target = plugin_dir / real.name
            if not target.exists():
                shutil.copy2(real, target, follow_symlinks=True)
            alias = plugin_dir / soname
            if alias != target and not alias.exists():
                alias.symlink_to(target.name)

    missing = [soname for soname in REQUIRED if not (qt_lib / soname).exists() and not list(root.rglob(soname))]
    if missing:
        raise SystemExit(f"bundled Qt lib dir is missing {', '.join(missing)} ({qt_lib})")

    unresolved: list[str] = []
    for plugin in plugins:
        if plugin.parent.name != "platforms":
            continue
        for line in subprocess.run(["ldd", str(plugin)], capture_output=True, text=True, check=False).stdout.splitlines():
            if "not found" in line:
                unresolved.append(f"{plugin.name}: {line.strip()}")
    if unresolved:
        raise SystemExit("platform plugins still have missing libraries:\n" + "\n".join(unresolved))
    print(f"bundled {len(set(copied))} system libraries into {qt_lib}")


if __name__ == "__main__":
    main()
