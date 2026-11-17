"""WP-8 release-surface checks for README, docs and unsigned install guidance."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ReleaseSurfaceTest(unittest.TestCase):
    def test_readme_and_index_share_the_four_pillar_story(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        index = (ROOT / "docs/index.md").read_text(encoding="utf-8")
        image = ROOT / "docs/assets/four-pillars.svg"
        self.assertTrue(image.is_file())
        for text in (readme, index):
            self.assertIn("four-pillars.svg", text)
            self.assertIn("AI 因子工坊", text)
            self.assertIn("确定性风洞", text)
            self.assertIn("SHAP", text)
            self.assertIn("Shadow-Run", text)
            self.assertIn("免 Token", text)
        for competitor in ("Backtrader", "VeighNa", "Qlib"):
            self.assertIn(competitor, readme)
        self.assertIn("| 维度 |", readme)

    def test_outdated_v05_status_phrases_are_absent(self) -> None:
        paths = [
            ROOT / "README.md",
            ROOT / "docs/index.md",
            ROOT / "docs/ai-development.md",
            ROOT / "docs/factors-and-ml.md",
            ROOT / "docs/initialization.md",
            ROOT / "docs/scope.md",
            ROOT / "docs/roadmap.md",
            ROOT / "docs/paper-trading.md",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for outdated in (
            "尚无“把任意 Python 文件放进目录即自动进入内置 ML 流程”",
            "30 分钟逐 bar 对照仍待补齐",
            "30 分钟影子逐 bar 生命周期",
        ):
            self.assertNotIn(outdated, text)

    def test_native_install_checks_and_unsigned_release_steps_are_first(self) -> None:
        text = (ROOT / "docs/native-installation.md").read_text(encoding="utf-8")
        check = text.index("## 先校验，再放行")
        macos = text.index("## macOS 安装")
        windows = text.index("## Windows 安装")
        self.assertLess(check, macos)
        self.assertLess(check, windows)
        for command in (
            "shasum -a 256 -c",
            "sha256sum -c",
            "Get-FileHash",
            "com.apple.quarantine",
            "Gatekeeper",
            "SmartScreen",
            "仍要打开",
            "仍要运行",
            "没有 Apple Developer ID/公证",
            "没有配置发行者证书",
        ):
            self.assertIn(command, text)


if __name__ == "__main__":
    unittest.main()
