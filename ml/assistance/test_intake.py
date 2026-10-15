"""Security and annotation tests; use `python3 -m unittest discover -s ml/assistance`."""
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image

from intake import annotations, audit_file, normalise, safe_extract, sha256, validate_entries


class IntakeTest(unittest.TestCase):
    def test_magic_detection_overrides_wrong_folder_and_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "misnamed.mp4"
            Image.new("RGB", (8, 6), "red").save(source, format="PNG")
            row = audit_file(source, "data/Q2_videos/Good/Hands_visible/misnamed.mp4", root, root)
            self.assertEqual(row["kind"], "photo")
            self.assertEqual(row["actual_format"], "PNG")
            self.assertTrue(row["decode_valid"])
            self.assertIn("media_type_disagrees_with_folder", row["issues"])

    def test_extraction_preserves_original_and_refuses_changed_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "input.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("data/Q2_photos/Good/a.jpg", b"original bytes")
            digest = sha256(archive)
            target = root / "dataset"
            safe_extract(archive, target, digest)
            safe_extract(archive, target, digest)
            original = target / "originals/data/Q2_photos/Good/a.jpg"
            self.assertEqual(original.read_bytes(), b"original bytes")
            original.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                safe_extract(archive, target, digest)
            self.assertEqual(original.read_bytes(), b"changed")
            self.assertEqual(sha256(archive), digest)

    def test_refuses_traversal_absolute_windows_symlink_encrypted_and_duplicates(self):
        for name in ("../x.jpg", "/x.jpg", "a/../../x.jpg", "C:/x.jpg", "a\\x.jpg"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_entries([zipfile.ZipInfo(name)])
        symlink = zipfile.ZipInfo("link")
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        encrypted = zipfile.ZipInfo("encrypted.jpg")
        encrypted.flag_bits = 1
        for entries in ([symlink], [encrypted], [zipfile.ZipInfo("a"), zipfile.ZipInfo("A")]):
            with self.assertRaises(ValueError):
                validate_entries(entries)

    def test_normalisation_preserves_distinct_framing_and_hand_labels(self):
        row = annotations("data/Q2_videos/ Good /Hands_not_visible/a.mp4")
        self.assertEqual(row["folder_quality_label"], "good")
        self.assertEqual(row["folder_hand_label"], "hands_not_visible")
        self.assertEqual(row["review_status"], "unreviewed")
        self.assertEqual(annotations("data/Q2_photos/Motion_blury/a.jpg")["folder_quality_label"], "motion_blurry")
        self.assertEqual(annotations("data/Q2_videos/ Out_of_frame /Hands_visible/a.mp4")["folder_hand_label"], "hands_visible")
        self.assertEqual(normalise("  Blurry  "), "blurry")


if __name__ == "__main__":
    unittest.main()
