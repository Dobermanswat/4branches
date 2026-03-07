from __future__ import annotations

import argparse
import base64
import bz2
import gzip
import hashlib
import json
import lzma
import re
import textwrap
import zlib
from pathlib import Path


def try_decompress(data: bytes) -> tuple[str, bytes] | None:
    methods = [
        ("zlib", lambda d: zlib.decompress(d)),
        ("gzip", lambda d: gzip.decompress(d)),
        ("bz2", lambda d: bz2.decompress(d)),
        ("lzma", lambda d: lzma.decompress(d)),
    ]
    for name, fn in methods:
        try:
            return name, fn(data)
        except Exception:
            continue
    return None


def extract_ascii_strings(data: bytes, min_len: int = 4) -> list[str]:
    pattern = re.compile(rb"[\x20-\x7E]{%d,}" % min_len)
    return [match.decode("ascii", errors="ignore") for match in pattern.findall(data)]


def extract_utf16le_strings(data: bytes, min_len: int = 4) -> list[str]:
    pattern = re.compile((rb"(?:[\x20-\x7E]\x00){%d,}" % min_len))
    out: list[str] = []
    for match in pattern.findall(data):
        try:
            out.append(match.decode("utf-16le"))
        except UnicodeDecodeError:
            continue
    return out


def write_lossless_text_dump(decoded: bytes, target: Path) -> None:
    b64_payload = base64.b64encode(decoded).decode("ascii")
    sha256 = hashlib.sha256(decoded).hexdigest()
    header = {
        "format": "ability-restored-bytes-base64",
        "byte_length": len(decoded),
        "sha256": sha256,
        "rebuild": "base64 -d < ability.json.restored.b64 > ability.json.restored.bin",
    }
    lines = ["# lossless text dump of restored bytes", json.dumps(header, ensure_ascii=False, indent=2), "", "## base64"]
    lines.extend(textwrap.wrap(b64_payload, width=120))
    target.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore/read ability.json.bytes")
    parser.add_argument("input", nargs="?", default="ability.json.bytes")
    parser.add_argument("--out-lossless", default="ability.json.restored.b64")
    parser.add_argument("--out-readable", default="ability.json.readable.txt")
    parser.add_argument("--out-bin", default=None, help="Optional raw binary output path")
    args = parser.parse_args()

    src = Path(args.input)
    raw_text = src.read_text(encoding="utf-8").strip()

    decoded = base64.b64decode(raw_text)
    write_lossless_text_dump(decoded, Path(args.out_lossless))

    if args.out_bin:
        Path(args.out_bin).write_bytes(decoded)

    maybe_decompressed = try_decompress(decoded)
    payload = decoded
    decompress_note = "none"
    if maybe_decompressed:
        decompress_note, payload = maybe_decompressed

    ascii_strings = extract_ascii_strings(payload)
    utf16_strings = extract_utf16le_strings(payload)
    identifier_like = sorted({x for x in ascii_strings if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{2,}", x)})

    report = {
        "source": str(src),
        "base64_length": len(raw_text),
        "decoded_length": len(decoded),
        "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
        "decompression": decompress_note,
        "ascii_strings_found": len(ascii_strings),
        "utf16le_strings_found": len(utf16_strings),
        "identifier_like_found": len(identifier_like),
    }

    lines = ["# ability.json.bytes восстановление", "", json.dumps(report, ensure_ascii=False, indent=2), ""]
    lines.append("## ASCII strings")
    lines.extend(ascii_strings if ascii_strings else ["(none)"])
    lines.append("")
    lines.append("## Identifier-like strings")
    lines.extend(identifier_like if identifier_like else ["(none)"])
    lines.append("")
    lines.append("## UTF-16LE strings")
    lines.extend(utf16_strings if utf16_strings else ["(none)"])
    Path(args.out_readable).write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote lossless text dump: {args.out_lossless}")
    print(f"Wrote readable report: {args.out_readable}")
    if args.out_bin:
        print(f"Wrote raw binary (optional): {args.out_bin}")


if __name__ == "__main__":
    main()
