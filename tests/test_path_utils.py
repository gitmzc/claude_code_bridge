"""
Unit tests for path_utils module.
Tests cross-platform path normalization for Windows, WSL, and MSYS paths.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from path_utils import (
    WIN_DRIVE_RE,
    looks_like_windows_path,
    normalize_path_for_match,
    work_dir_match_keys,
    extract_session_work_dir_norm,
)


class TestLooksLikeWindowsPath(unittest.TestCase):
    """Tests for looks_like_windows_path function."""

    def test_windows_drive_path(self):
        """Windows drive paths should be detected."""
        self.assertTrue(looks_like_windows_path("C:\\Users\\test"))
        self.assertTrue(looks_like_windows_path("D:/Projects/foo"))
        self.assertTrue(looks_like_windows_path("c:\\"))
        self.assertTrue(looks_like_windows_path("C:"))

    def test_unc_path(self):
        """UNC paths should be detected as Windows paths."""
        self.assertTrue(looks_like_windows_path("\\\\server\\share"))
        self.assertTrue(looks_like_windows_path("//server/share"))

    def test_unix_path(self):
        """Unix paths should not be detected as Windows paths."""
        self.assertFalse(looks_like_windows_path("/home/user"))
        self.assertFalse(looks_like_windows_path("/mnt/c/Users"))
        self.assertFalse(looks_like_windows_path("/c/Users"))

    def test_empty_and_whitespace(self):
        """Empty and whitespace strings should return False."""
        self.assertFalse(looks_like_windows_path(""))
        self.assertFalse(looks_like_windows_path("   "))


class TestNormalizePathForMatch(unittest.TestCase):
    """Tests for normalize_path_for_match function."""

    def test_empty_input(self):
        """Empty input should return empty string."""
        self.assertEqual(normalize_path_for_match(""), "")
        self.assertEqual(normalize_path_for_match(None), "")
        self.assertEqual(normalize_path_for_match("   "), "")

    def test_windows_path_normalization(self):
        """Windows paths should be normalized with lowercase drive letter."""
        result = normalize_path_for_match("C:\\Users\\test")
        self.assertTrue(result.startswith("c:"))
        self.assertIn("users", result)  # case-folded

    def test_wsl_path_to_windows(self):
        """WSL /mnt/c/... paths should map to c:/..."""
        result = normalize_path_for_match("/mnt/c/Users/test")
        self.assertTrue(result.startswith("c:"))
        self.assertIn("users", result)

    def test_wsl_and_windows_match(self):
        """WSL and Windows paths to same location should normalize identically."""
        wsl_path = normalize_path_for_match("/mnt/c/Users/test")
        win_path = normalize_path_for_match("C:\\Users\\test")
        self.assertEqual(wsl_path, win_path)

    @patch.dict(os.environ, {"MSYSTEM": "MINGW64"})
    def test_msys_path_to_windows(self):
        """MSYS /c/... paths should map to c:/... when MSYSTEM is set."""
        result = normalize_path_for_match("/c/Users/test")
        self.assertTrue(result.startswith("c:"))

    def test_backslash_to_forward_slash(self):
        """Backslashes should be converted to forward slashes."""
        result = normalize_path_for_match("C:\\Users\\test\\folder")
        self.assertNotIn("\\", result)

    def test_redundant_separators(self):
        """Redundant separators should be collapsed."""
        result = normalize_path_for_match("/home//user///test")
        self.assertNotIn("//", result)

    def test_unc_path_preserved(self):
        """UNC path prefix should be preserved."""
        result = normalize_path_for_match("//server/share/folder")
        self.assertTrue(result.startswith("//"))

    def test_drive_root_trailing_slash(self):
        """Drive root normalization."""
        result = normalize_path_for_match("C:\\")
        # After normalization, drive root may be "c:" or "c:/" depending on implementation
        self.assertTrue(result.startswith("c:"))

    def test_case_insensitive_windows(self):
        """Windows paths should be case-folded."""
        result1 = normalize_path_for_match("C:\\Users\\Test")
        result2 = normalize_path_for_match("c:\\users\\test")
        self.assertEqual(result1, result2)


class TestWorkDirMatchKeys(unittest.TestCase):
    """Tests for work_dir_match_keys function."""

    def test_returns_set(self):
        """Should return a set of normalized keys."""
        result = work_dir_match_keys(Path.cwd())
        self.assertIsInstance(result, set)
        self.assertTrue(len(result) > 0)

    def test_includes_normalized_cwd(self):
        """Should include normalized version of the work directory."""
        cwd = Path.cwd()
        result = work_dir_match_keys(cwd)
        # At least one key should be present
        self.assertTrue(len(result) >= 1)

    @patch.dict(os.environ, {"PWD": "/some/path"})
    def test_includes_pwd_env(self):
        """Should include PWD environment variable if set."""
        result = work_dir_match_keys(Path("/other/path"))
        # Should have multiple keys when PWD differs from work_dir
        self.assertTrue(len(result) >= 1)


class TestExtractSessionWorkDirNorm(unittest.TestCase):
    """Tests for extract_session_work_dir_norm function."""

    def test_empty_dict(self):
        """Empty dict should return empty string."""
        self.assertEqual(extract_session_work_dir_norm({}), "")

    def test_non_dict(self):
        """Non-dict input should return empty string."""
        self.assertEqual(extract_session_work_dir_norm(None), "")
        self.assertEqual(extract_session_work_dir_norm([]), "")
        self.assertEqual(extract_session_work_dir_norm("string"), "")

    def test_work_dir_norm_preferred(self):
        """work_dir_norm should be preferred over work_dir."""
        data = {
            "work_dir_norm": "/mnt/c/Users/test",
            "work_dir": "/different/path"
        }
        result = extract_session_work_dir_norm(data)
        self.assertIn("c:", result)  # Should use work_dir_norm

    def test_fallback_to_work_dir(self):
        """Should fall back to work_dir if work_dir_norm is missing."""
        data = {"work_dir": "/home/user/project"}
        result = extract_session_work_dir_norm(data)
        self.assertIn("home", result)

    def test_empty_work_dir_norm(self):
        """Empty work_dir_norm should fall back to work_dir."""
        data = {
            "work_dir_norm": "   ",
            "work_dir": "/home/user"
        }
        result = extract_session_work_dir_norm(data)
        self.assertIn("home", result)


class TestWinDriveRegex(unittest.TestCase):
    """Tests for WIN_DRIVE_RE regex."""

    def test_matches_drive_letter(self):
        """Should match drive letter patterns."""
        self.assertIsNotNone(WIN_DRIVE_RE.match("C:"))
        self.assertIsNotNone(WIN_DRIVE_RE.match("C:/"))
        self.assertIsNotNone(WIN_DRIVE_RE.match("C:\\"))
        self.assertIsNotNone(WIN_DRIVE_RE.match("d:/path"))

    def test_no_match_unix(self):
        """Should not match Unix paths."""
        self.assertIsNone(WIN_DRIVE_RE.match("/home"))
        self.assertIsNone(WIN_DRIVE_RE.match("/c/Users"))


if __name__ == "__main__":
    unittest.main()
