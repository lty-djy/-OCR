from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtGui import QColor, QImage

from inksnip_ocr.main_window import read_local_image


class LocalImageTests(unittest.TestCase):
    def test_reads_png_file(self) -> None:
        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "测试图片.png"
            source = QImage(12, 8, QImage.Format.Format_RGB32)
            source.fill(QColor("#36a66b"))
            self.assertTrue(source.save(str(image_path)))

            loaded = read_local_image(str(image_path))

            self.assertFalse(loaded.isNull())
            self.assertEqual((loaded.width(), loaded.height()), (12, 8))

    def test_missing_file_reports_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "不存在"):
            read_local_image("Z:/不存在/图片.png")


if __name__ == "__main__":
    unittest.main()
