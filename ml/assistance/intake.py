#!/usr/bin/env python3
"""Local-only, bounded Q2/Q3 intake. Never writes private media into Git.

Requires Python 3.10+, Pillow, ffmpeg and ffprobe. Original names/bytes stay intact.
Folder annotations remain UNVERIFIED. Thumbnails/fingerprints are review aids,
never ground truth, confirmed duplicates, or independent samples.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import re
import shutil
import stat
import subprocess
import unicodedata
import zipfile
import zlib
from pathlib import Path, PurePosixPath

from PIL import Image, ImageDraw, ImageOps

PROTOCOL = "proxy-intake-v2"
REPO = Path(__file__).resolve().parents[2]
QUALITY = {"good": "good", "dark": "dark", "blurry": "blurry",
           "motion_blury": "motion_blurry", "motion_blurry": "motion_blurry",
           "shaky": "motion_blurry", "out_of_frame": "out_of_frame"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalise(value: str) -> str:
    return re.sub(r"[\s-]+", "_", unicodedata.normalize("NFKC", value).strip().casefold())


def validate_entries(entries: list[zipfile.ZipInfo]) -> None:
    """Reject ambiguous/unsafe entries before creating any extraction directory."""
    seen = set()
    if len(entries) > 10000 or sum(x.file_size for x in entries) > 20_000_000_000:
        raise ValueError("Archive exceeds intake limits")
    for entry in entries:
        name = entry.filename
        parts = PurePosixPath(name).parts
        mode = entry.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if (not parts or name.startswith("/") or "\\" in name or ":" in name
                or ".." in parts or "\x00" in name or entry.flag_bits & 1
                or kind not in (0, stat.S_IFREG, stat.S_IFDIR)
                or entry.file_size > 2_000_000_000):
            raise ValueError(f"Unsafe ZIP entry: {name!r}")
        canonical = str(PurePosixPath(name)).casefold()
        if canonical in seen:
            raise ValueError(f"Duplicate/ambiguous ZIP name: {name!r}")
        seen.add(canonical)


def safe_extract(archive: Path, root: Path, digest: str) -> list[str]:
    if root.resolve().is_relative_to(REPO):
        raise ValueError("Dataset root must be outside the repository")
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        validate_entries(entries)
        if root.exists() and not (root / "archive.json").exists() and any(root.iterdir()):
            raise ValueError("Use a new empty task directory; refusing an unrelated existing directory")
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            raise ValueError("Dataset root must not be a symlink")
        marker = root / "archive.json"
        if marker.exists() and json.loads(marker.read_text())["sha256"] != digest:
            raise ValueError("Dataset root belongs to another archive")
        originals = root / "originals"
        names = []
        for entry in entries:
            destination = originals / entry.filename
            # Resolve every destination, including pre-existing symlink parents.
            if not destination.resolve().is_relative_to(originals.resolve()) or originals.is_symlink():
                raise ValueError("Destination escapes originals")
            if entry.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            names.append(entry.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if not destination.is_file() or destination.is_symlink():
                    raise ValueError("Unsafe existing destination")
                crc = 0
                with destination.open("rb") as f:
                    for b in iter(lambda: f.read(1024 * 1024), b""):
                        crc = zlib.crc32(b, crc)
                if destination.stat().st_size != entry.file_size or crc != entry.CRC:
                    raise ValueError("Existing original differs; refusing overwrite")
            else:
                with z.open(entry) as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target, 128 * 1024)
        marker.write_text(json.dumps({"archive_name": archive.name, "sha256": digest,
                                      "protocol": PROTOCOL}, indent=2) + "\n")
        return sorted(names)


def command(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout, check=False)


def fingerprint(image: Image.Image) -> str:
    pixels = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS).tobytes()
    value = 0
    for y in range(8):
        for x in range(8):
            value = (value << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return f"{value:016x}"


def thumbnail(image: Image.Image, root: Path, identity: str, suffix: str) -> dict:
    image = image.convert("RGB")
    image.thumbnail((256, 192))
    image.save(root / f"{identity}-{suffix}.jpg", quality=85)
    return {"dhash64": fingerprint(image),
            "dhash64_rotations": [fingerprint(image.rotate(a, expand=True)) for a in (0, 90, 180, 270)]}


def annotations(name: str) -> dict:
    parts = PurePosixPath(name).parts
    normal = [normalise(p) for p in parts]
    photo = "q2_photos" in normal
    video = "q2_videos" in normal
    if photo == video:
        raise ValueError(f"Unrecognised folder structure: {name}")
    pos = normal.index("q2_photos" if photo else "q2_videos")
    quality = QUALITY.get(normal[pos + 1])
    hand = normal[pos + 2] if video else "not_labelled"
    if quality is None or (video and hand not in ("hands_visible", "hands_not_visible")):
        raise ValueError(f"Unrecognised annotation: {name}")
    hint = re.search(r"(?:IMG|VID)-(\d{8})-WA", parts[-1], re.I)
    return {"kind": "photo" if photo else "video", "original_quality_category": parts[pos + 1],
            "folder_quality_label": quality, "folder_hand_label": hand,
            "label_provenance": "dataset_owner_folder_unverified", "review_status": "unreviewed",
            "source_device": None, "source_session": None,
            "filename_date_hint": hint.group(1) if hint else None,
            "messaging_filename_hint": hint is not None}


def audit_file(path: Path, name: str, thumbnails: Path, logs: Path) -> dict:
    digest = sha256(path)
    row = {"id": "m-" + hashlib.sha256(name.encode()).hexdigest()[:12], "relative_path": name,
           "sha256": digest, "bytes": path.stat().st_size, **annotations(name),
           "decode_valid": False, "fingerprints": [], "issues": []}
    try:
        row["folder_kind"] = row["kind"]
        # Folder and extension are annotations, not media-type detection. An actual
        # MP4 in Q2_photos must still be probed/decoded as video and reviewed separately.
        try:
            with Image.open(path) as detected:
                row["kind"] = "photo"
        except (OSError, ValueError):
            row["kind"] = "video"
        if row["kind"] != row["folder_kind"]:
            row["issues"].append("media_type_disagrees_with_folder")
        if row["kind"] == "photo":
            with Image.open(path) as im:
                row.update(actual_format=im.format, encoded_width=im.width, encoded_height=im.height)
                im.verify()
            with Image.open(path) as im:
                im.load()  # every image is fully decoded, not just a bounds probe
                exif = im.getexif()
                row["orientation"] = int(exif.get(274, 1))
                row["exif_present"] = bool(exif)
                row["source_device"] = " ".join(str(exif.get(k, "")).strip() for k in (271, 272)).strip() or None
                row["source_capture_time"] = exif.get(36867) or exif.get(306)
                row["software"] = str(exif.get(305, "")) or None
                oriented = ImageOps.exif_transpose(im)
                row.update(width=oriented.width, height=oriented.height, decode_valid=True)
                row["fingerprints"] = [{"timestamp_ms": None, **thumbnail(oriented, thumbnails, row["id"], "photo")}]
        else:
            probe = command(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
            if probe.returncode:
                raise ValueError("ffprobe failed")
            metadata = json.loads(probe.stdout)
            stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
            fmt = metadata["format"]
            rotation = next((d.get("rotation") for d in stream.get("side_data_list", []) if "rotation" in d), None)
            row.update(actual_format=fmt.get("format_name"), codec=stream.get("codec_name"),
                       width=stream["width"], height=stream["height"],
                       duration_ms=round(float(stream.get("duration", fmt["duration"])) * 1000),
                       fps=stream.get("avg_frame_rate"), nominal_fps=stream.get("r_frame_rate"),
                       rotation=rotation if rotation is not None else stream.get("tags", {}).get("rotate", 0),
                       pixel_format=stream.get("pix_fmt"), encoded_frames=stream.get("nb_frames"),
                       encoder=fmt.get("tags", {}).get("encoder"),
                       creation_time=fmt.get("tags", {}).get("creation_time"),
                       source_device=fmt.get("tags", {}).get("com.android.model"))
            # Full sequential decode to the null muxer; no whole-video buffers or extracted-frame tree.
            decoded = command(["ffmpeg", "-v", "error", "-xerror", "-err_detect", "explode", "-threads", "1",
                               "-i", str(path), "-map", "0:v:0", "-an", "-f", "null", "-"], timeout=900)
            (logs / f"{row['id']}.decode.txt").write_bytes(decoded.stderr)
            row["decode_valid"] = decoded.returncode == 0
            if decoded.returncode:
                row["issues"].append("full_video_decode_failed")
            for index, time_ms in enumerate(sorted(set([0, row["duration_ms"] // 2, max(0, row["duration_ms"] - 500)]))):
                frame = command(["ffmpeg", "-v", "error", "-threads", "1", "-ss", str(time_ms / 1000),
                                 "-i", str(path), "-frames:v", "1", "-vf", "scale=256:192:force_original_aspect_ratio=decrease",
                                 "-f", "image2pipe", "-vcodec", "mjpeg", "-"])
                if frame.returncode == 0 and frame.stdout:
                    with Image.open(io.BytesIO(frame.stdout)) as im:
                        row["fingerprints"].append({"timestamp_ms": time_ms,
                            **thumbnail(im, thumbnails, row["id"], str(index))})
                else:
                    row["issues"].append(f"review_frame_failed:{time_ms}")
    except (OSError, ValueError, KeyError, StopIteration, subprocess.TimeoutExpired) as error:
        row["issues"].append(type(error).__name__ + ":" + str(error)[:180])
    return row


def contact_sheets(rows: list[dict], thumbnails: Path, output: Path) -> None:
    for kind in ("photo", "video"):
        for category in sorted(set(r["folder_quality_label"] for r in rows)):
            selected = [r for r in rows if r["kind"] == kind and r["folder_quality_label"] == category]
            for page in range(0, len(selected), 12):
                subset = selected[page:page + 12]
                sheet = Image.new("RGB", (4 * 280, ((len(subset) + 3) // 4) * 240), "#eeeeee")
                draw = ImageDraw.Draw(sheet)
                for i, row in enumerate(subset):
                    x, y = (i % 4) * 280, (i // 4) * 240
                    files = sorted(thumbnails.glob(row["id"] + "-*.jpg"))
                    if files:
                        with Image.open(files[0]) as im:
                            sheet.paste(im, (x, y))
                    draw.text((x + 2, y + 194), row["id"], fill="black")
                    draw.text((x + 2, y + 208), Path(row["relative_path"]).name, fill="black")
                    draw.text((x + 2, y + 222), row["folder_hand_label"], fill="black")
                sheet.save(output / f"{kind}-{category}-{page // 12 + 1}.jpg")


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=REPO / "ml")
    args = parser.parse_args()
    digest = sha256(args.zip)
    names = safe_extract(args.zip, args.dataset_root, digest)
    derived = args.dataset_root / "review"
    thumbnails, logs, sheets = (derived / x for x in ("thumbnails", "decode_logs", "sheets"))
    for directory in (thumbnails, logs, sheets):
        directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, name in enumerate(names):
        row = audit_file(args.dataset_root / "originals" / name, name, thumbnails, logs)
        rows.append(row)
        print(f"{index + 1}/{len(names)} {row['id']} {row['kind']} decode={row['decode_valid']}", flush=True)
    hashes = collections.defaultdict(list)
    for row in rows:
        hashes[row["sha256"]].append(row["id"])
    candidates = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a["sha256"] == b["sha256"]:
                continue
            distances = [(int(hx, 16) ^ int(hy, 16)).bit_count()
                         for x in a["fingerprints"] for y in b["fingerprints"]
                         for hx in x["dhash64_rotations"] for hy in y["dhash64_rotations"]]
            if distances and min(distances) <= 12:
                candidates.append({"a": a["id"], "b": b["id"], "min_dhash_distance": min(distances),
                                   "status": "candidate_requires_visual_review"})
    manifest = args.output_root / "quality/data/manifest.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    common = {"protocol": PROTOCOL, "archive_sha256": digest, "manifest_sha256": sha256(manifest),
              "raw_media": len(rows), "raw_photos": sum(r["kind"] == "photo" for r in rows),
              "raw_videos": sum(r["kind"] == "video" for r in rows),
              "decode_valid": sum(r["decode_valid"] for r in rows),
              "exact_unique_hashes": len(hashes),
              "exact_duplicate_groups": [v for v in hashes.values() if len(v) > 1],
              "folder_counts": dict(collections.Counter(f"{r['kind']}/{r['folder_quality_label']}/{r['folder_hand_label']}" for r in rows)),
              "source_devices_confirmed_by_metadata": sorted(set(r["source_device"] for r in rows if r["source_device"])),
              "metadata_device_missing": sum(not r["source_device"] for r in rows),
              "messaging_filename_hints": sum(r["messaging_filename_hint"] for r in rows),
              "near_duplicate_candidates": len(candidates), "accepted_unique_media": None,
              "near_duplicate_rule": "minimum dHash64 distance <=12 across 4 rotations and review timestamps; review candidates only",
              "media_type_folder_mismatches": [r["id"] for r in rows if r["kind"] != r["folder_kind"]],
              "labels_verified": False, "splits_frozen": False,
              "limits": ["Folder labels are unverified owner annotations.",
                         "Messaging filenames/dates do not prove capture dates, sessions, or phone count.",
                         "DHash similarity is a review aid, not proof of independent or duplicate captures.",
                         "No accepted sample count until visual review and conservative grouping."]}
    write_json(args.output_root / "quality/data/audit.json", common)
    write_json(args.output_root / "quality/data/near_duplicate_candidates.json", candidates)
    for module in ("quality", "hands"):
        target = args.output_root / module / "data/initial_labels.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="") as f:
            fields = ["id", "relative_path", "sha256", "folder_quality_label", "folder_hand_label",
                      "label_provenance", "review_status", "verified_quality_labels", "source_group"]
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows({key: row.get(key, "") for key in fields} for row in rows
                             if module == "quality" or row["kind"] == "video")
    contact_sheets(rows, thumbnails, sheets)
    print(json.dumps(common, indent=2), flush=True)


if __name__ == "__main__":
    main()
