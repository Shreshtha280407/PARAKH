#!/usr/bin/env python3
"""Check the Android app's EN/HI string resources for parity and for drift
against the canonical declaration contract (packs/ae-con-q0602/mapping).

Usage: python tools/check_android_string_parity.py
Exit 0 if every check passes, exit 1 otherwise.

This is a static, non-emulator check -- it reads XML and JSON directly, so
it runs in CI without an Android SDK/emulator. It checks:

  [parity]   values/*.xml and values-hi/*.xml define the exact same set of
             string names in each of strings.xml, card_labels.xml and
             task_titles.xml -- no string translated in only one language
             (a missing or stray translation renders a blank/placeholder to
             a real worker on-device, English lint's MissingTranslation
             check can be suppressed but this script cannot be)
  [nonempty] every string value (in both locales) is non-empty after
             trimming -- catches an accidentally-blank translation that
             would still pass [parity] (the key exists, the text doesn't)
  [contract] card_labels.xml (both locales) defines EXACTLY one
             card_label_<id> per card/tool id in
             packs/ae-con-q0602/mapping/links.json, no more, no fewer --
             catches the Android resource layer silently drifting from the
             20-card + 6-tool JSON contract (e.g. a card added to links.json
             without a matching Android string, or a stale string left
             behind for a card that was removed)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
RES_EN = ROOT / "apps/android/app/src/main/res/values"
RES_HI = ROOT / "apps/android/app/src/main/res/values-hi"
LINKS_PATH = ROOT / "packs/ae-con-q0602/mapping/links.json"

STRING_FILES = ["strings.xml", "card_labels.xml", "task_titles.xml"]

STRING_TAG_RE = re.compile(r'<string\s+name="([^"]+)"[^>]*>(.*?)</string>', re.DOTALL)


def parse_strings(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    return {m.group(1): m.group(2) for m in STRING_TAG_RE.finditer(text)}


def check_parity():
    problems = []
    checked_files = 0
    for filename in STRING_FILES:
        en = parse_strings(RES_EN / filename)
        hi = parse_strings(RES_HI / filename)
        if not en and not hi:
            problems.append(f"{filename}: neither values/ nor values-hi/ defines this file")
            continue
        checked_files += 1
        en_only = sorted(set(en) - set(hi))
        hi_only = sorted(set(hi) - set(en))
        if en_only:
            problems.append(f"{filename}: in values/ only (missing Hindi translation): {', '.join(en_only)}")
        if hi_only:
            problems.append(f"{filename}: in values-hi/ only (stray/orphaned translation): {', '.join(hi_only)}")
    if not problems:
        return True, f"[parity]   values/ and values-hi/ define the same string names across {checked_files} files ✓"
    return False, "[parity]   " + "; ".join(problems) + " ✗"


def check_nonempty():
    problems = []
    checked = 0
    for res_dir, locale in ((RES_EN, "values"), (RES_HI, "values-hi")):
        for filename in STRING_FILES:
            for name, value in parse_strings(res_dir / filename).items():
                checked += 1
                if not value.strip():
                    problems.append(f"{locale}/{filename}:{name} is empty")
    if not problems:
        return True, f"[nonempty] all {checked} string values (both locales) are non-empty ✓"
    return False, "[nonempty] " + "; ".join(problems) + " ✗"


def check_contract():
    if not LINKS_PATH.exists():
        return False, f"[contract] missing {LINKS_PATH} ✗"
    import json

    links = json.loads(LINKS_PATH.read_text())
    expected_ids = sorted(
        item["id"] for group in ("cards", "tools") for item in links.get(group, [])
    )
    problems = []
    for res_dir, locale in ((RES_EN, "values"), (RES_HI, "values-hi")):
        labels = parse_strings(res_dir / "card_labels.xml")
        label_ids = sorted(
            name[len("card_label_"):].upper()
            for name in labels
            if name.startswith("card_label_")
        )
        missing = sorted(set(expected_ids) - set(label_ids))
        extra = sorted(set(label_ids) - set(expected_ids))
        if missing:
            problems.append(f"{locale}/card_labels.xml missing label(s) for: {', '.join(missing)}")
        if extra:
            problems.append(f"{locale}/card_labels.xml has stray label(s) for removed id(s): {', '.join(extra)}")
    if not problems:
        return True, (f"[contract] card_labels.xml (both locales) has exactly one label per "
                       f"links.json id ({len(expected_ids)} ids) ✓")
    return False, "[contract] " + "; ".join(problems) + " ✗"


def main():
    checks = [check_parity(), check_nonempty(), check_contract()]
    failed = 0
    for ok, line in checks:
        print(line)
        if not ok:
            failed += 1
    if failed:
        print(f"--- {failed} check(s) failed --- exit 1")
        sys.exit(1)


if __name__ == "__main__":
    main()
