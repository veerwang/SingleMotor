"""app_config 本机配置持久化测试"""

import json

from nimotion.models.app_config import (
    load_di_invert,
    load_direction_inverted,
    save_di_invert,
    save_direction_inverted,
)


class TestDirectionInvertedConfig:
    def test_missing_file_defaults_false(self, tmp_path):
        assert load_direction_inverted(tmp_path / "none.json") is False

    def test_corrupt_file_defaults_false(self, tmp_path):
        path = tmp_path / "motor_config.json"
        path.write_text("{broken", encoding="utf-8")
        assert load_direction_inverted(path) is False

    def test_save_load_roundtrip(self, tmp_path):
        path = tmp_path / "motor_config.json"
        save_direction_inverted(True, path)
        assert load_direction_inverted(path) is True
        save_direction_inverted(False, path)
        assert load_direction_inverted(path) is False

    def test_save_preserves_other_fields(self, tmp_path):
        path = tmp_path / "motor_config.json"
        path.write_text(
            json.dumps({"other": 123}), encoding="utf-8"
        )
        save_direction_inverted(True, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["other"] == 123
        assert data["direction_inverted"] is True


class TestDiInvertConfig:
    def test_missing_file_defaults_false(self, tmp_path):
        assert load_di_invert(tmp_path / "none.json") is False

    def test_corrupt_file_defaults_false(self, tmp_path):
        path = tmp_path / "motor_config.json"
        path.write_text("{broken", encoding="utf-8")
        assert load_di_invert(path) is False

    def test_save_load_roundtrip(self, tmp_path):
        path = tmp_path / "motor_config.json"
        save_di_invert(True, path)
        assert load_di_invert(path) is True
        save_di_invert(False, path)
        assert load_di_invert(path) is False

    def test_save_preserves_other_fields(self, tmp_path):
        path = tmp_path / "motor_config.json"
        path.write_text(json.dumps({"direction_inverted": True}), encoding="utf-8")
        save_di_invert(True, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["direction_inverted"] is True
        assert data["di_invert"] is True
