from __future__ import annotations

import argparse
import base64
import bz2
import gzip
import hashlib
import json
import lzma
import math
import re
import textwrap
import zlib
from collections import Counter
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


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((v / n) * math.log2(v / n) for v in counts.values())


def extract_ascii_strings(data: bytes, min_len: int = 8) -> list[str]:
    pattern = re.compile(rb"[\x20-\x7E]{%d,}" % min_len)
    return [match.decode("ascii", errors="ignore") for match in pattern.findall(data)]


def extract_utf16le_strings(data: bytes, min_len: int = 6) -> list[str]:
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
    rebuild_out = target.with_suffix(".bin").name
    header = {
        "format": "restored-bytes-base64",
        "byte_length": len(decoded),
        "sha256": sha256,
        "rebuild": f"base64 -d < {target.name} > {rebuild_out}",
    }
    lines = ["# lossless text dump of restored bytes", json.dumps(header, ensure_ascii=False, indent=2), "", "## base64"]
    lines.extend(textwrap.wrap(b64_payload, width=120))
    target.write_text("\n".join(lines), encoding="utf-8")


def detect_magic(data: bytes) -> str | None:
    checks = [
        (b"\x1bLua", "lua_bytecode"),
        (b"{", "json_object"),
        (b"[", "json_array"),
        (b"PK\x03\x04", "zip"),
        (b"\x1f\x8b", "gzip"),
        (b"BZh", "bz2"),
        (b"\xfd7zXZ\x00", "xz"),
    ]
    for sig, name in checks:
        if data.startswith(sig):
            return name
    return None


def analyze_transform_attempts(decoded: bytes) -> list[dict[str, str]]:
    attempts: list[tuple[str, bytes]] = [("raw", decoded), ("reversed", decoded[::-1])]

    # cheap xor scan: only keys that produce known header signatures on first bytes
    sig_headers = [b"\x1bLua", b"{", b"[", b"PK\x03\x04", b"\x1f\x8b", b"BZh", b"\xfd7zXZ\x00"]
    for key in range(256):
        prefix = bytes(b ^ key for b in decoded[:8])
        if any(prefix.startswith(sig) for sig in sig_headers):
            attempts.append((f"xor_byte_{key}", bytes(b ^ key for b in decoded)))

    results: list[dict[str, str]] = []
    for name, payload in attempts:
        magic = detect_magic(payload)
        decomp = try_decompress(payload)
        item: dict[str, str] = {"attempt": name, "magic": magic or "none"}
        if decomp:
            method, out = decomp
            item["decompress"] = method
            item["out_len"] = str(len(out))
            item["out_magic"] = detect_magic(out) or "none"
            item["status"] = "interesting"
        elif magic:
            item["decompress"] = "none"
            item["status"] = "interesting"
        else:
            item["decompress"] = "none"
            item["status"] = "noise"
        results.append(item)

    # unique + prefer interesting
    uniq: list[dict[str, str]] = []
    seen = set()
    for r in sorted(results, key=lambda x: (x["status"] != "interesting", x["attempt"])):
        key = (r["magic"], r.get("decompress", "none"), r.get("out_magic", "none"))
        if key in seen and r["status"] != "interesting":
            continue
        seen.add(key)
        uniq.append(r)
    return uniq[:20]


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore/read *.json.bytes payloads")
    parser.add_argument("input", nargs="?", default="ability.json.bytes")
    parser.add_argument("--out-lossless", default="ability.json.restored.b64")
    parser.add_argument("--out-readable", default="ability.json.readable.txt")
    parser.add_argument("--out-bin", default=None, help="Optional raw binary output path")
    parser.add_argument("--ascii-min-len", type=int, default=10)
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

    ascii_strings = extract_ascii_strings(payload, min_len=args.ascii_min_len)
    utf16_strings = extract_utf16le_strings(payload)
    identifier_like = sorted({x for x in ascii_strings if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{2,}", x)})

    entropy = shannon_entropy(decoded)
    likely_obfuscated = decompress_note == "none" and entropy > 7.9
    attempts = analyze_transform_attempts(decoded)
    solved_by_attempts = any(a["status"] == "interesting" and (a["magic"] not in {"json_object", "json_array", "none"} or a["decompress"] != "none") for a in attempts)

    report = {
        "source": str(src),
        "base64_length": len(raw_text),
        "decoded_length": len(decoded),
        "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
        "decoded_entropy": round(entropy, 4),
        "decompression": decompress_note,
        "likely_obfuscated_or_encrypted": likely_obfuscated,
        "ascii_min_len": args.ascii_min_len,
        "ascii_strings_found": len(ascii_strings),
        "utf16le_strings_found": len(utf16_strings),
        "identifier_like_found": len(identifier_like),
        "advanced_attempts": len(attempts),
        "advanced_attempts_found_structured_decode": solved_by_attempts,
    }

    lines = [f"# {src.name} восстановление", "", json.dumps(report, ensure_ascii=False, indent=2), ""]
    if likely_obfuscated:
        lines.extend(
            [
                "## Note",
                "Данные выглядят как обфусцированные/зашифрованные (высокая энтропия, стандартная распаковка не сработала).",
                "Ниже — только извлечённые текстовые фрагменты, это НЕ полноценная расшифровка структуры.",
                "",
            ]
        )

    lines.append("## Advanced transform attempts")
    for a in attempts:
        parts = [
            f"attempt={a['attempt']}",
            f"status={a['status']}",
            f"magic={a['magic']}",
            f"decompress={a['decompress']}",
        ]
        if "out_len" in a:
            parts.append(f"out_len={a['out_len']}")
        if "out_magic" in a:
            parts.append(f"out_magic={a['out_magic']}")
        lines.append("; ".join(parts))

    lines.append("")
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
