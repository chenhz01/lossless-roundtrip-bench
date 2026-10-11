#!/usr/bin/env python3
"""lossless-roundtrip-bench (lrb) -- a roundtrip fidelity benchmark for
document codecs, generic edition: read -> mutate -> save -> re-read -> diff.

The benchmark asks one question of any (de)serializer pair: after a harmless
edit and a save, does re-reading give back exactly what was there before?
For text: byte identity. For JSON: deep key/value identity, plus a
double-save instability check (save -> load -> save must not drift).

Pure stdlib. Ships a deliberately lossy demo codec to prove detection works.
"""
from __future__ import annotations

import argparse
import json
import sys

VERSION = "0.1.1"
PROBE_KEY = "_lrb_probe"
PROBE_TEXT_MARK = "\u27f2 lrb roundtrip probe"


def deep_diff(a, b, path=""):
    """Walk two structures; yield (kind, path, detail).
    kind: lost | added | changed."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            p = f"{path}.{k}" if path else str(k)
            if k not in b:
                out.append(("lost", p, f"{k!r} present before, absent after"))
            else:
                out += deep_diff(a[k], b[k], p)
        for k in b:
            if k not in a:
                out.append(("added", f"{path}.{k}" if path else str(k), f"{k!r} appeared after"))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(("changed", path or "$", f"list length {len(a)} -> {len(b)}"))
        for i, (x, y) in enumerate(zip(a, b)):
            out += deep_diff(x, y, f"{path}[{i}]")
    else:
        if a != b:
            sa, sb = repr(a), repr(b)
            out.append(("changed", path or "$",
                        f"{sa[:60]}{'...' if len(sa) > 60 else ''} -> "
                        f"{sb[:60]}{'...' if len(sb) > 60 else ''}"))
    return out


# ---------------------------------------------------------------------------
# Codecs. Each: load(bytes) -> doc, save(doc) -> bytes, plus a mutate(doc).
# ---------------------------------------------------------------------------

def _mutate_json(doc):
    if not isinstance(doc, dict):
        raise ValueError("json mutation expects a dict root (array roots: wrap first)")
    doc[PROBE_KEY] = "probe"
    return doc


def _mutate_text(text):
    return PROBE_TEXT_MARK + "\n" + text


def _lossy_save(doc):
    """Deliberately lossy demo: floats truncate to int, tuples of pairs fold
    into dicts. Use ONLY to verify the benchmark detects loss."""
    def walk(x):
        if isinstance(x, float):
            return int(x)
        if isinstance(x, dict):
            return {str(k): walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    return json.dumps(walk(json.loads(json.dumps(doc))), ensure_ascii=False, indent=2).encode("utf-8")


CODECS = {
    "text": {
        "load": lambda raw: raw.decode("utf-8"),
        "save": lambda doc: doc.encode("utf-8"),
        "mutate": _mutate_text,
        "byte_compare": True,
        "note": "byte-identity roundtrip",
    },
    "json": {
        "load": lambda raw: json.loads(raw.decode("utf-8")),
        "save": lambda doc: json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"),
        "mutate": _mutate_json,
        "byte_compare": False,
        "note": "deep key/value identity + double-save instability check",
    },
    "lossy-demo": {
        "load": lambda raw: json.loads(raw.decode("utf-8")),
        "save": _lossy_save,
        "mutate": _mutate_json,
        "byte_compare": False,
        "note": "deliberately lossy (floats -> int): proves detection works",
    },
}


def run_bench(codec_name: str, raw: bytes) -> dict:
    if codec_name not in CODECS:
        raise KeyError(f"unknown codec {codec_name!r}; available: {sorted(CODECS)}")
    codec = CODECS[codec_name]
    report = {"codec": codec_name, "note": codec["note"], "ok": True, "score_percent": 100.0,
              "bytes_in": len(raw)}
    try:
        doc1 = codec["load"](raw)
    except Exception as e:
        return {"codec": codec_name, "ok": False, "error": f"load failed: {e}",
                "score_percent": 0.0}
    try:
        doc2 = codec["mutate"](doc1)
    except ValueError as e:
        return {"codec": codec_name, "ok": False, "error": str(e), "score_percent": 0.0}
    saved1 = codec["save"](doc2)
    reloaded1 = codec["load"](saved1)

    if codec["byte_compare"]:
        diffs = deep_diff(doc2, reloaded1)
        # save must be a fixed point: re-saving the reloaded doc changes nothing
        report["byte_identity_after_probe"] = (codec["save"](reloaded1) == saved1)
    else:
        diffs = deep_diff(doc2, reloaded1)
        saved2 = codec["save"](reloaded1)
        reloaded2 = codec["load"](saved2)
        drift = deep_diff(reloaded1, reloaded2)
        if drift:
            diffs += [("changed", "$instability", f"double-save drift: {len(drift)} diffs")]

    lost = [d for d in diffs if d[0] == "lost"]
    changed = [d for d in diffs if d[0] == "changed"]
    added = [d for d in diffs if d[0] == "added"]
    # the probe itself is expected as "added"; anything else is loss
    real_added = [d for d in added if PROBE_KEY not in d[1] and PROBE_TEXT_MARK not in d[2]]
    total_issues = len(lost) + len(changed) + len(real_added)
    report.update({
        "bytes_out": len(saved1),
        "diff_count": total_issues,
        "lost": lost, "changed": changed, "added_unexpected": real_added,
        "score_percent": round(100.0 * (1 - min(1.0, total_issues / max(1, len(lost) + len(changed) + len(added)))), 2),
        "verdict": "LOSSLESS" if total_issues == 0 else "LOSSY",
    })
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _fmt(r: dict) -> str:
    if not r.get("ok"):
        return f"error: {r['error']}"
    lines = [f"codec={r['codec']}  verdict={r['verdict']}  score={r['score_percent']}%  "
             f"bytes {r['bytes_in']} -> {r['bytes_out']}  diffs={r['diff_count']}"]
    for kind, path, detail in (r["lost"] + r["changed"] + r["added_unexpected"])[:10]:
        lines.append(f"  [{kind}] {path}: {detail}")
    if r["diff_count"] > 10:
        lines.append(f"  ... and {r['diff_count'] - 10} more")
    return "\n".join(lines)


def _cmd_bench(args) -> int:
    try:
        raw = open(args.file, "rb").read()
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    r = run_bench(args.codec, raw)
    if not r.get("ok"):
        print(f"error: {r['error']}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(_fmt(r))
    if args.strict and r["verdict"] != "LOSSLESS":
        return 1
    return 0


def _cmd_codecs(_args) -> int:
    for name, c in CODECS.items():
        print(f"{name:<12} {c['note']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lrb", description="lossless roundtrip benchmark (generic)")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bench", help="read -> mutate -> save -> re-read -> diff")
    b.add_argument("--codec", choices=sorted(CODECS), default="json")
    b.add_argument("file")
    b.add_argument("--json", action="store_true", help="machine-readable report")
    b.add_argument("--strict", action="store_true", help="exit 1 when verdict is LOSSY")
    b.set_defaults(func=_cmd_bench)
    sub.add_parser("codecs", help="list available codecs").set_defaults(func=_cmd_codecs)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
