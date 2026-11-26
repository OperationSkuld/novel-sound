#!/usr/bin/env python3
"""Verify a TrollStore IPA: ZIP integrity, metadata and fakesignatures.

Usage: python3 scripts/verify_ios_trollstore_ipa.py <ipa> [sha256-file] [expected-version]
"""
from __future__ import annotations

import hashlib
import plistlib
import struct
import sys
import zipfile
from pathlib import Path

LC_CODE_SIGNATURE = 0x1D
THIN_MAGICS = {
    b"\xce\xfa\xed\xfe": ("<", False),
    b"\xcf\xfa\xed\xfe": ("<", True),
    b"\xfe\xed\xfa\xce": (">", False),
    b"\xfe\xed\xfa\xcf": (">", True),
}
FAT_MAGICS = {
    b"\xca\xfe\xba\xbe": (">", False),
    b"\xbe\xba\xfe\xca": ("<", False),
    b"\xca\xfe\xba\xbf": (">", True),
    b"\xbf\xba\xfe\xca": ("<", True),
}


def macho_slices(data: bytes):
    magic = data[:4]
    if magic in FAT_MAGICS:
        endian, wide = FAT_MAGICS[magic]
        count = struct.unpack_from(endian + "I", data, 4)[0]
        entry_size = 32 if wide else 20
        for i in range(count):
            base = 8 + i * entry_size
            if wide:
                offset, size = struct.unpack_from(endian + "QQ", data, base + 8)
            else:
                offset, size = struct.unpack_from(endian + "II", data, base + 8)
            yield data[offset:offset + size]
    elif magic in THIN_MAGICS:
        yield data


def has_code_signature(data: bytes) -> bool:
    for image in macho_slices(data):
        magic = image[:4]
        if magic not in THIN_MAGICS:
            continue
        endian, wide = THIN_MAGICS[magic]
        cmd_count = struct.unpack_from(endian + "I", image, 16)[0]
        offset = 32 if wide else 28
        for _ in range(cmd_count):
            if offset + 8 > len(image):
                break
            cmd, size = struct.unpack_from(endian + "II", image, offset)
            if cmd == LC_CODE_SIGNATURE:
                return True
            if size < 8:
                break
            offset += size
    return False


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    ipa = Path(sys.argv[1])
    if not ipa.is_file():
        print(f"missing IPA: {ipa}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(ipa.read_bytes()).hexdigest()
    print(f"IPA: {ipa} ({ipa.stat().st_size} bytes)")
    print(f"SHA-256: {digest}")

    if len(sys.argv) > 2:
        expected = Path(sys.argv[2]).read_text().strip().split()[0]
        if expected != digest:
            print("ERROR: checksum mismatch", file=sys.stderr)
            return 1
        print("Checksum matches sidecar file")
    expected_version = sys.argv[3] if len(sys.argv) > 3 else None

    with zipfile.ZipFile(ipa) as zf:
        bad = zf.testzip()
        if bad:
            print(f"ERROR: corrupt ZIP entry: {bad}", file=sys.stderr)
            return 1
        names = zf.namelist()
        prefix = "Payload/Runner.app/"
        if prefix + "Info.plist" not in names:
            print("ERROR: Payload/Runner.app/Info.plist missing", file=sys.stderr)
            return 1
        info = plistlib.loads(zf.read(prefix + "Info.plist"))
        print("Bundle ID:", info.get("CFBundleIdentifier"))
        print("Version:", info.get("CFBundleShortVersionString"), info.get("CFBundleVersion"))
        if info.get("CFBundleIdentifier") != "com.fqapp.fqapp":
            print("ERROR: unexpected bundle identifier", file=sys.stderr)
            return 1
        if expected_version and info.get("CFBundleShortVersionString") != expected_version:
            print(f"ERROR: unexpected version (expected {expected_version})", file=sys.stderr)
            return 1

        machos = {}
        for name in names:
            if name.endswith("/"):
                continue
            data = zf.read(name)
            if data[:4] in THIN_MAGICS or data[:4] in FAT_MAGICS:
                machos[name] = data
        signed = [name for name, data in machos.items() if has_code_signature(data)]
        if prefix + "Runner" not in signed:
            print("ERROR: main executable is not fakesigned", file=sys.stderr)
            return 1
        print(f"Mach-O binaries: {len(machos)}, fakesigned: {len(signed)}")
        if len(signed) != len(machos):
            print("ERROR: some Mach-O binaries are unsigned", file=sys.stderr)
            return 1
    print("OK: TrollStore IPA structure and signatures verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
