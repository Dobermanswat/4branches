#!/usr/bin/env python3
"""Recover and pretty-print JSON from encoded/compressed/binary input."""
from __future__ import annotations

import argparse
import base64
import binascii
import bz2
import gzip
import json
import lzma
import pathlib
import shutil
import subprocess
import tempfile
import zlib
from collections import deque
from dataclasses import dataclass
from typing import Callable


MAX_DEPTH = 4
MAX_CANDIDATES = 500


@dataclass(frozen=True)
class Candidate:
    label: str
    payload: bytes
    depth: int


def _try(fn: Callable[[], bytes]) -> bytes | None:
    try:
        out = fn()
    except Exception:
        return None
    return out


def _append_if_new(
    queue: deque[Candidate],
    seen: set[bytes],
    parent: Candidate,
    label: str,
    payload: bytes | None,
) -> None:
    if not payload or payload == parent.payload or payload in seen:
        return
    seen.add(payload)
    queue.append(Candidate(f"{parent.label} -> {label}", payload, parent.depth + 1))


def _transforms(c: Candidate, queue: deque[Candidate], seen: set[bytes]) -> None:
    if c.depth >= MAX_DEPTH:
        return

    p = c.payload
    _append_if_new(queue, seen, c, "base64", _try(lambda: base64.b64decode(p, validate=False)))
    _append_if_new(queue, seen, c, "base64(urlsafe)", _try(lambda: base64.urlsafe_b64decode(p)))

    compact = b"".join(p.split())
    if compact != p:
        _append_if_new(queue, seen, c, "strip-whitespace", compact)

    # hex encoded content
    if len(compact) % 2 == 0:
        _append_if_new(queue, seen, c, "hex", _try(lambda: binascii.unhexlify(compact)))

    _append_if_new(queue, seen, c, "gzip", _try(lambda: gzip.decompress(p)))
    _append_if_new(queue, seen, c, "bz2", _try(lambda: bz2.decompress(p)))
    _append_if_new(queue, seen, c, "lzma", _try(lambda: lzma.decompress(p)))
    _append_if_new(queue, seen, c, "zlib", _try(lambda: zlib.decompress(p)))
    _append_if_new(queue, seen, c, "zlib(raw)", _try(lambda: zlib.decompress(p, -zlib.MAX_WBITS)))
    _append_if_new(queue, seen, c, "rar", _try(lambda: _rar_extract_first_file(p)))


def _rar_extract_first_file(payload: bytes) -> bytes:
    rar4 = b"Rar!\x1a\x07\x00"
    rar5 = b"Rar!\x1a\x07\x01\x00"
    if not (payload.startswith(rar4) or payload.startswith(rar5)):
        raise ValueError("Not a RAR archive")

    with tempfile.TemporaryDirectory() as td:
        archive_path = pathlib.Path(td) / "input.rar"
        archive_path.write_bytes(payload)

        commands: list[list[str]] = []
        if shutil.which("unrar"):
            commands.append(["unrar", "p", "-inul", str(archive_path)])
        if shutil.which("7z"):
            commands.append(["7z", "x", "-so", str(archive_path)])
        if shutil.which("bsdtar"):
            commands.append(["bsdtar", "-xOf", str(archive_path)])

        if not commands:
            raise RuntimeError("No RAR extractor found (unrar/7z/bsdtar)")

        for cmd in commands:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout

    raise RuntimeError("Failed to extract RAR archive")


def _json_from_text(text: str) -> object | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped[0] not in "[{\"-0123456789tfn":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _decode_json(payload: bytes) -> tuple[str, object] | None:
    for enc in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1251", "latin-1"):
        try:
            text = payload.decode(enc)
        except UnicodeDecodeError:
            continue
        parsed = _json_from_text(text)
        if parsed is not None:
            return enc, parsed

    # carve a possible JSON object/array from inside a binary blob
    for start_char in (b"{", b"["):
        start = payload.find(start_char)
        if start == -1:
            continue
        for end_char in (b"}", b"]"):
            end = payload.rfind(end_char)
            if end <= start:
                continue
            chunk = payload[start : end + 1]
            for enc in ("utf-8", "cp1251", "latin-1"):
                try:
                    text = chunk.decode(enc)
                except UnicodeDecodeError:
                    continue
                parsed = _json_from_text(text)
                if parsed is not None:
                    return f"{enc} (carved)", parsed
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover and pretty-print JSON from damaged/encoded input")
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("-o", "--output", type=pathlib.Path, default=pathlib.Path("recovered.json"))
    parser.add_argument("--report", type=pathlib.Path, default=pathlib.Path("recovery-report.txt"))
    args = parser.parse_args()

    raw = args.input.read_bytes()
    queue: deque[Candidate] = deque([Candidate("raw", raw, 0)])
    seen: set[bytes] = {raw}
    attempts = 0

    report_lines = [f"Input: {args.input}", f"Raw bytes: {len(raw)}", f"Depth limit: {MAX_DEPTH}", ""]

    while queue and attempts < MAX_CANDIDATES:
        c = queue.popleft()
        attempts += 1
        report_lines.append(f"Attempt: {c.label} | depth={c.depth} | size={len(c.payload)}")

        parsed = _decode_json(c.payload)
        if parsed:
            enc, data = parsed
            args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report_lines.append(f"SUCCESS: decoded as {enc}; pretty JSON written to {args.output}")
            report_lines.append(f"Attempts used: {attempts}")
            args.report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
            print(f"Recovered JSON via: {c.label} ({enc}) -> {args.output}")
            return 0

        _transforms(c, queue, seen)

    report_lines.extend(
        [
            "",
            f"No JSON recovered after {attempts} attempts.",
            "Likely encrypted or stored in custom binary format.",
        ]
    )
    args.report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"Failed to recover JSON. Report: {args.report}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
