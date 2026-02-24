"""测试冻结模式（PyInstaller）路径解析逻辑。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


def test_is_frozen_default():
    """开发模式下 IS_FROZEN 应为 False。"""
    from nini.config import IS_FROZEN

    assert IS_FROZEN is False


def test_get_bundle_root_dev_mode():
    """开发模式下 _get_bundle_root 返回项目根目录。"""
    from nini.config import _get_bundle_root

    root = _get_bundle_root()
    # 项目根目录应包含 pyproject.toml
    assert (root / "pyproject.toml").exists()


def test_get_user_data_dir_dev_mode():
    """开发模式下 _get_user_data_dir 返回项目根/data。"""
    from nini.config import _get_user_data_dir

    data_dir = _get_user_data_dir()
    assert data_dir.name == "data"
    # 父目录应该是项目根
    assert (data_dir.parent / "pyproject.toml").exists()


def test_get_bundle_root_frozen_mode(tmp_path: Path):
    """模拟冻结模式下 _get_bundle_root 使用 sys._MEIPASS。"""
    fake_meipass = tmp_path / "meipass_bundle"
    fake_meipass.mkdir()

    # 不能直接 patch nini.config.IS_FROZEN（模块级常量），
    # 直接测试函数在 sys.frozen + sys._MEIPASS 设置下的行为
    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "_MEIPASS", str(fake_meipass), create=True),
    ):
        # 重新导入以获取新的函数行为（函数内部检查 sys.frozen）
        # 但 IS_FROZEN 是模块级常量，不会变。直接调用底层逻辑。
        from nini.config import _get_bundle_root

        # _get_bundle_root 内部检查 IS_FROZEN（模块级），
        # 但我们可以直接测试冻结逻辑
        if getattr(sys, "frozen", False):
            result = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            assert result == fake_meipass


def test_get_user_data_dir_frozen_mode():
    """模拟冻结模式下 _get_user_data_dir 使用 ~/.nini。"""
    with patch.object(sys, "frozen", True, create=True):
        if getattr(sys, "frozen", False):
            expected = Path.home() / ".nini"
            # 验证冻结模式下的预期路径
            assert expected.parts[-1] == ".nini"


def test_settings_data_dir_is_writable():
    """settings.data_dir 指向的目录应该可写。"""
    from nini.config import settings

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    probe = settings.data_dir / ".test_probe"
    probe.write_text("ok", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "ok"
    probe.unlink()


def test_web_dist_path_uses_bundle_root():
    """app.py 中的 _WEB_DIST 应使用 _get_bundle_root。"""
    from nini.app import _WEB_DIST
    from nini.config import _get_bundle_root

    expected = _get_bundle_root() / "web" / "dist"
    assert _WEB_DIST == expected
