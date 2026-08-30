#!/usr/bin/env python3
"""
ffx-downgrade.py — Downgrade Adobe After Effects .ffx preset files
to an older AE version by patching the version marker byte inside
the file.

Works on Linux (e.g. CachyOS), macOS, and Windows. Requires only
Python 3, no external packages.

How it works (verified against the actual source of the FFX-Downgrader
project, github.com/Kisev2/FFX-Downgrader — Main.py / FFX-Dg.py):

A .ffx file is a RIFX container. There is NO fixed offset for the
version marker — instead, the file is scanned byte by byte from the
start, looking for the first byte whose value matches one of the
known "version byte" values below AND whose corresponding version is
newer than the target. That single byte is patched in place; nothing
else in the file is touched.

Confirmed byte values (from the real source code):
    2025 -> 0x60
    2024 -> 0x5F
    2023 -> 0x5E
    2022 -> 0x5D

There are no confirmed values for 2020/2021, so this script does not
support those targets. Guessing extra byte values for this scanning
approach is risky: a wrong guess can coincidentally match an unrelated
byte elsewhere in the file and corrupt it in a different, harder-to-spot
way (this is likely what happened with the previous version of this
script, which patched a fixed offset that actually overlapped the
RIFX container's size field).
"""

import sys
from pathlib import Path

# --- Confirmed version -> byte value (verified from the real source) ----
VERSION_BYTES = {
    2025: 0x60,
    2024: 0x5F,
    2023: 0x5E,
    2022: 0x5D,
}

REVERSE_VERSION_BYTES = {v: k for k, v in VERSION_BYTES.items()}


def find_ffx_files(path: Path):
    """Returns a list of .ffx files, whether path is a file or a folder."""
    if path.is_file():
        if path.suffix.lower() != ".ffx":
            print(f"Warning: {path} doesn't look like a .ffx file, skipping.")
            return []
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.ffx"))
    print(f"Error: {path} does not exist.")
    return []


def scan_and_patch(data: bytearray, target_year: int, target_byte: int):
    """
    Scans the file byte by byte for the first byte whose value matches a
    known version marker AND whose version is newer than target_year.
    Patches that single byte in place. Returns (patched: bool, found_year
    or None) where found_year is the version the marker indicated before
    patching (None if nothing matching was found at all).
    """
    for i in range(len(data)):
        val = data[i]
        if val in REVERSE_VERSION_BYTES:
            current_year = REVERSE_VERSION_BYTES[val]
            if current_year <= target_year:
                # Already at or below target — keep scanning in case an
                # earlier/different marker exists, matching original tool.
                continue
            data[i] = target_byte
            return True, current_year
    return False, None


def process_file(src: Path, target_year: int, out_dir: Path):
    target_byte = VERSION_BYTES[target_year]
    data = bytearray(src.read_bytes())

    if data[0:4] != b"RIFX":
        raise ValueError("Not a valid FFX file (missing RIFX header).")

    patched, found_year = scan_and_patch(data, target_year, target_byte)

    if patched:
        print(f"  {src.name}: found AE {found_year} marker -> patched to {target_year}")
        new_data = bytes(data)
    else:
        # No marker newer than target was found — either it's already at
        # or below the target version, or no recognizable marker exists.
        print(f"  {src.name}: no marker above AE {target_year} found — copied as-is "
              f"(likely already at or below target version).")
        new_data = bytes(data)

    stem = src.stem
    out_name = f"{stem}-ae{target_year}.ffx"
    out_path = out_dir / out_name

    # Avoid accidentally overwriting an existing file
    counter = 1
    while out_path.exists():
        out_path = out_dir / f"{stem}-ae{target_year}_{counter}.ffx"
        counter += 1

    out_path.write_bytes(new_data)
    return out_path


def prompt_input_path() -> tuple[Path, list]:
    """Step 1: ask for the file or folder containing the .ffx file(s)."""
    while True:
        ans = input("1) Path to a .ffx file OR a folder containing .ffx files: ").strip()
        # Allow users to paste paths with surrounding quotes
        ans = ans.strip('"').strip("'")
        if not ans:
            print("   Please enter a path.\n")
            continue
        path = Path(ans).expanduser()
        if not path.exists():
            print(f"   '{path}' doesn't exist. Try again.\n")
            continue
        files = find_ffx_files(path)
        if not files:
            print("   No .ffx files found there. Try again.\n")
            continue
        print(f"   Found {len(files)} .ffx file(s).\n")
        return path, files


def prompt_target_version() -> int:
    """Step 2: ask which AE version to downgrade to."""
    versions = sorted(VERSION_BYTES.keys(), reverse=True)
    options = ", ".join(str(v) for v in versions)
    while True:
        ans = input(f"2) Downgrade to which After Effects version? ({options}): ").strip()
        try:
            year = int(ans)
        except ValueError:
            print("   Please enter a year, e.g. 2023.\n")
            continue
        if year not in VERSION_BYTES:
            print(f"   Unsupported version (no confirmed byte value for it yet). "
                  f"Choose one of: {options}\n")
            continue
        print()
        return year


def prompt_output_dir(default: Path) -> Path:
    """Step 3: ask where to save the downgraded file(s)."""
    while True:
        ans = input(f"3) Where do you want to save the result? [{default}]: ").strip()
        ans = ans.strip('"').strip("'")
        out = Path(ans).expanduser() if ans else default
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"   Couldn't create/use that folder: {e}\n")
            continue
        print()
        return out


def main():
    print("=== FFX Downgrader ===\n")

    src_path, files = prompt_input_path()
    target_year = prompt_target_version()

    default_out = src_path.parent / "ffx-downgraded" if src_path.is_file() else src_path / "downgraded"
    out_dir = prompt_output_dir(default_out)

    print(f"Saving to: {out_dir}\n")

    results = []
    for f in files:
        try:
            out_path = process_file(f, target_year, out_dir)
            results.append(out_path)
        except Exception as e:
            print(f"  Error processing {f}: {e}")

    print(f"\nDone. {len(results)} file(s) saved to {out_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
