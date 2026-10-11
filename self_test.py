#!/usr/bin/env python3
"""Self-test for lossless-roundtrip-bench: functional / error-path / extreme-edge."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lrb  # noqa: E402

RESULTS = []
CASES = []


def case(name):
    def deco(fn):
        def wrapper():
            try:
                fn()
                RESULTS.append((name, "PASS", ""))
            except AssertionError as e:
                RESULTS.append((name, "FAIL", str(e)))
            except Exception as e:  # noqa: BLE001
                RESULTS.append((name, "FAIL", f"{type(e).__name__}: {e}"))
        CASES.append(wrapper)
        return wrapper
    return deco


def tmpfile(content: bytes, suffix=".txt"):
    td = tempfile.mkdtemp()
    p = os.path.join(td, "f" + suffix)
    open(p, "wb").write(content)
    return p


SAMPLE = json.dumps({
    "title": "Report", "meta": {"author": "agent", "rev": 2},
    "score": 97.5, "tags": ["a", "b"], "nested": {"deep": {"leaf": True}},
}).encode("utf-8")


# ---------------- functional ----------------

@case("func/json-roundtrip-lossless")
def _():
    r = lrb.run_bench("json", SAMPLE)
    assert r["verdict"] == "LOSSLESS" and r["diff_count"] == 0, r


@case("func/nested-keys-preserved")
def _():
    r = lrb.run_bench("json", SAMPLE)
    paths = [d[1] for d in r["lost"] + r["changed"]]
    assert "nested.deep.leaf" not in str(paths)


@case("func/lossy-codec-detected")
def _():
    r = lrb.run_bench("lossy-demo", SAMPLE)
    assert r["verdict"] == "LOSSY", r
    assert any("score" in d[1] for d in r["changed"]), r


@case("func/text-byte-identity")
def _():
    r = lrb.run_bench("text", b"line one\nline two\n")
    assert r["verdict"] == "LOSSLESS" and r["byte_identity_after_probe"] is True


@case("func/double-save-stability-json")
def _():
    r = lrb.run_bench("json", SAMPLE)
    assert not any("instability" in d[1] for d in r["changed"]), r


@case("func/cli-bench-strict-exit-codes")
def _():
    here = HERE
    jf = tmpfile(SAMPLE, ".json")
    rc_ok = subprocess.run([sys.executable, "lrb.py", "bench", "--codec", "json", jf, "--strict"],
                           capture_output=True, cwd=here)
    assert rc_ok.returncode == 0, rc_ok.stderr
    lf = tmpfile(SAMPLE, ".json")
    rc_bad = subprocess.run([sys.executable, "lrb.py", "bench", "--codec", "lossy-demo",
                             lf, "--strict"], capture_output=True, cwd=here)
    assert rc_bad.returncode == 1, rc_bad.stderr


@case("func/cli-codecs-list")
def _():
    rc = subprocess.run([sys.executable, "lrb.py", "codecs"], capture_output=True, cwd=HERE)
    assert b"lossy-demo" in rc.stdout and rc.returncode == 0


# ---------------- error paths ----------------

@case("err/corrupt-json-clean-error-exit-2")
def _():
    p = tmpfile(b"{ definitely not json ]]]")
    rc = subprocess.run([sys.executable, "lrb.py", "bench", "--codec", "json", p],
                        capture_output=True, cwd=HERE)
    assert rc.returncode == 2, rc.returncode
    assert b"load failed" in rc.stderr


@case("err/json-array-root-mutation-rejected")
def _():
    r = lrb.run_bench("json", json.dumps([1, 2, 3]).encode())
    assert not r["ok"] and "dict root" in r["error"], r


@case("err/unknown-codec")
def _():
    p = tmpfile(SAMPLE, ".json")
    rc = subprocess.run([sys.executable, "lrb.py", "bench", "--codec", "xml", p],
                        capture_output=True, cwd=HERE)
    assert rc.returncode == 2, rc.returncode


@case("err/missing-file-exit-3")
def _():
    rc = subprocess.run([sys.executable, "lrb.py", "bench", "--codec", "json", "ghost.json"],
                        capture_output=True, cwd=HERE)
    assert rc.returncode == 3, rc.returncode


# ---------------- extreme edges ----------------

@case("edge/empty-file-text-lossless")
def _():
    r = lrb.run_bench("text", b"")
    assert r["verdict"] == "LOSSLESS", r


@case("edge/empty-file-json-fails-cleanly")
def _():
    r = lrb.run_bench("json", b"")
    assert not r["ok"] and "load failed" in r["error"], r


@case("edge/huge-json-1mib-lossless")
def _():
    big = {"k%06d" % i: {"v": i, "f": i + 0.5, "s": "x" * 10} for i in range(30000)}
    raw = json.dumps(big).encode()
    assert len(raw) > 1_000_000, len(raw)
    r = lrb.run_bench("json", raw)
    assert r["verdict"] == "LOSSLESS", (r.get("diff_count"), r.get("changed", [])[:3])


@case("edge/unicode-content-preserved")
def _():
    doc = {"emoji": "🚀中文", "quote": '"quotes" \\ backslash'}
    r = lrb.run_bench("json", json.dumps(doc, ensure_ascii=False).encode("utf-8"))
    assert r["verdict"] == "LOSSLESS", r


@case("edge/deeply-nested-200-levels")
def _():
    doc = {}
    cur = doc
    for i in range(200):
        cur["n"] = {}
        cur = cur["n"]
    cur["leaf"] = 1
    r = lrb.run_bench("json", json.dumps(doc).encode())
    assert r["verdict"] == "LOSSLESS", r


@case("edge/lossy-detection-counts-not-vague")
def _():
    doc = {"a": 1.2, "b": 3.7, "c": "str", "d": [1.5, 2.5]}
    r = lrb.run_bench("lossy-demo", json.dumps(doc).encode())
    assert len(r["changed"]) >= 3, r  # a, b, and list elements


def main() -> int:
    for fn in CASES:
        fn()
    width = max(len(n) for n, _, _ in RESULTS)
    for name, status, msg in RESULTS:
        print(f"{name:<{width}}  {status}" + (f"  ({msg})" if msg else ""))
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    print(f"\n{passed}/{len(RESULTS)} passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
