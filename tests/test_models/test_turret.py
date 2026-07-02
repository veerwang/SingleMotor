"""物镜转盘模型单元测试"""

import pytest

from nimotion.models.turret import (
    BACKLASH_MAX_DEG,
    GEAR_RATIO,
    MICROSTEP_REG_ADDR,
    MOTOR_STEPS_PER_REV,
    POSITION_TOLERANCE,
    TurretPosition,
    backlash_deg_to_pulses,
    calculate_position_pulses,
    calculate_pulses_per_position,
    effective_position_pulses,
    load_backlash_deg,
    load_calibration,
    microstep_from_register,
    pulse_to_turret_position,
    save_backlash_deg,
    save_calibration,
)


class TestConstants:
    def test_gear_ratio(self):
        assert GEAR_RATIO == 2.75

    def test_motor_steps_per_rev(self):
        assert MOTOR_STEPS_PER_REV == 200

    def test_position_tolerance(self):
        assert POSITION_TOLERANCE == 50

    def test_microstep_reg_addr(self):
        assert MICROSTEP_REG_ADDR == 0x001A


class TestTurretPosition:
    def test_values(self):
        assert TurretPosition.UNKNOWN == -1
        assert TurretPosition.POS_1 == 0
        assert TurretPosition.POS_2 == 1
        assert TurretPosition.POS_3 == 2
        assert TurretPosition.POS_4 == 3

    def test_count(self):
        assert len(TurretPosition) == 5


class TestMicrostepFromRegister:
    @pytest.mark.parametrize(
        "reg_value, expected",
        [(0, 1), (1, 2), (2, 4), (3, 8), (4, 16), (5, 32), (6, 64), (7, 128)],
    )
    def test_valid_values(self, reg_value: int, expected: int):
        assert microstep_from_register(reg_value) == expected

    @pytest.mark.parametrize("invalid", [-1, 8, 100, -10])
    def test_invalid_values(self, invalid: int):
        with pytest.raises(ValueError):
            microstep_from_register(invalid)


class TestCalculatePulsesPerPosition:
    def test_microstep_128(self):
        # 200 * 128 = 25600 pulses/rev; 25600 * 2.75 / 4 = 17600
        assert calculate_pulses_per_position(128) == 17600

    def test_microstep_1(self):
        # 200 * 1 = 200 pulses/rev; 200 * 2.75 / 4 = 137.5 → int = 137
        assert calculate_pulses_per_position(1) == 137

    def test_microstep_16(self):
        # 200 * 16 = 3200 pulses/rev; 3200 * 2.75 / 4 = 2200
        assert calculate_pulses_per_position(16) == 2200

    def test_microstep_32(self):
        # 200 * 32 = 6400 pulses/rev; 6400 * 2.75 / 4 = 4400
        assert calculate_pulses_per_position(32) == 4400


class TestCalculatePositionPulses:
    def test_microstep_128(self):
        pp = calculate_position_pulses(128)
        assert pp[TurretPosition.POS_1] == 0
        assert pp[TurretPosition.POS_2] == 17600
        assert pp[TurretPosition.POS_3] == 35200
        assert pp[TurretPosition.POS_4] == 52800

    def test_microstep_16(self):
        pp = calculate_position_pulses(16)
        assert pp[TurretPosition.POS_1] == 0
        assert pp[TurretPosition.POS_2] == 2200
        assert pp[TurretPosition.POS_3] == 4400
        assert pp[TurretPosition.POS_4] == 6600

    def test_all_positions_mapped(self):
        pp = calculate_position_pulses(128)
        for pos in TurretPosition:
            if pos != TurretPosition.UNKNOWN:
                assert pos in pp

    def test_unknown_not_in_map(self):
        pp = calculate_position_pulses(128)
        assert TurretPosition.UNKNOWN not in pp


class TestPulseToTurretPosition:
    @pytest.fixture()
    def position_pulses(self) -> dict[TurretPosition, int]:
        return calculate_position_pulses(128)

    def test_exact_positions(self, position_pulses):
        assert pulse_to_turret_position(0, position_pulses) == TurretPosition.POS_1
        assert pulse_to_turret_position(17600, position_pulses) == TurretPosition.POS_2
        assert pulse_to_turret_position(35200, position_pulses) == TurretPosition.POS_3
        assert pulse_to_turret_position(52800, position_pulses) == TurretPosition.POS_4

    def test_within_tolerance(self, position_pulses):
        assert pulse_to_turret_position(50, position_pulses) == TurretPosition.POS_1
        assert pulse_to_turret_position(-50, position_pulses) == TurretPosition.POS_1
        assert pulse_to_turret_position(17600 + 49, position_pulses) == TurretPosition.POS_2
        assert pulse_to_turret_position(17600 - 50, position_pulses) == TurretPosition.POS_2
        assert pulse_to_turret_position(35200 + 30, position_pulses) == TurretPosition.POS_3
        assert pulse_to_turret_position(52800 - 1, position_pulses) == TurretPosition.POS_4

    def test_outside_tolerance(self, position_pulses):
        assert pulse_to_turret_position(51, position_pulses) == TurretPosition.UNKNOWN
        assert pulse_to_turret_position(-51, position_pulses) == TurretPosition.UNKNOWN
        assert pulse_to_turret_position(17600 + 51, position_pulses) == TurretPosition.UNKNOWN
        assert pulse_to_turret_position(8800, position_pulses) == TurretPosition.UNKNOWN

    def test_boundary_exact(self, position_pulses):
        """容差边界精确测试: ±50 内匹配，±51 不匹配。"""
        for pos, target in position_pulses.items():
            assert pulse_to_turret_position(target + 50, position_pulses) == pos
            assert pulse_to_turret_position(target - 50, position_pulses) == pos
            assert pulse_to_turret_position(target + 51, position_pulses) == TurretPosition.UNKNOWN
            assert pulse_to_turret_position(target - 51, position_pulses) == TurretPosition.UNKNOWN

    def test_large_offset(self, position_pulses):
        assert pulse_to_turret_position(100000, position_pulses) == TurretPosition.UNKNOWN
        assert pulse_to_turret_position(-100000, position_pulses) == TurretPosition.UNKNOWN

    def test_different_microstep(self):
        """使用不同细分数验证脉冲匹配。"""
        pp = calculate_position_pulses(16)
        assert pulse_to_turret_position(0, pp) == TurretPosition.POS_1
        assert pulse_to_turret_position(2200, pp) == TurretPosition.POS_2
        assert pulse_to_turret_position(4400, pp) == TurretPosition.POS_3
        assert pulse_to_turret_position(6600, pp) == TurretPosition.POS_4
        # 原来 microstep=128 的 17600 在 microstep=16 下应该 UNKNOWN
        assert pulse_to_turret_position(17600, pp) == TurretPosition.UNKNOWN


class TestCalibration:
    """孔位标定持久化与有效位置计算。"""

    def test_load_missing_file_returns_empty(self, tmp_path):
        assert load_calibration(tmp_path / "nope.json") == {}

    def test_save_then_load_roundtrip(self, tmp_path):
        f = tmp_path / "calib.json"
        calib = {
            TurretPosition.POS_1: 300,
            TurretPosition.POS_2: 2500,
            TurretPosition.POS_3: 4700,
            TurretPosition.POS_4: 6900,
        }
        save_calibration(calib, f)
        assert load_calibration(f) == calib

    def test_load_ignores_unknown_and_bad_values(self, tmp_path):
        f = tmp_path / "calib.json"
        f.write_text('{"0": 100, "1": "oops", "-1": 5}', encoding="utf-8")
        loaded = load_calibration(f)
        assert loaded == {TurretPosition.POS_1: 100}

    def test_load_corrupt_json_returns_empty(self, tmp_path):
        f = tmp_path / "calib.json"
        f.write_text("{not json", encoding="utf-8")
        assert load_calibration(f) == {}

    def test_effective_no_calibration_uses_theoretical(self):
        assert effective_position_pulses(16, None) == calculate_position_pulses(16)
        assert effective_position_pulses(16, {}) == calculate_position_pulses(16)

    def test_effective_partial_calibration_falls_back(self):
        # 只标定了 POS_1（回零点≠孔位1），其余回退理论值
        eff = effective_position_pulses(16, {TurretPosition.POS_1: 350})
        theo = calculate_position_pulses(16)
        assert eff[TurretPosition.POS_1] == 350
        assert eff[TurretPosition.POS_2] == theo[TurretPosition.POS_2]
        assert eff[TurretPosition.POS_3] == theo[TurretPosition.POS_3]
        assert eff[TurretPosition.POS_4] == theo[TurretPosition.POS_4]


class TestBacklash:
    """回程间隙补偿：角度持久化 + 角度→脉冲换算。"""

    def test_deg_to_pulses_microstep16(self):
        # 转盘整圈=8800脉冲(ms16), 1° = 8800/360 ≈ 24.44 → 24
        assert backlash_deg_to_pulses(1.0, 16) == 24
        assert backlash_deg_to_pulses(0.0, 16) == 0
        assert backlash_deg_to_pulses(0.5, 16) == 12  # 12.22 → 12

    def test_deg_to_pulses_scales_with_microstep(self):
        # ms32 整圈=17600, 1° ≈ 48.9 → 49
        assert backlash_deg_to_pulses(1.0, 32) == 49

    def test_load_missing_returns_zero(self, tmp_path):
        assert load_backlash_deg(tmp_path / "none.json") == 0.0

    def test_save_load_roundtrip(self, tmp_path):
        f = tmp_path / "bl.json"
        save_backlash_deg(0.37, f)
        assert load_backlash_deg(f) == 0.37

    def test_clamped_to_range(self, tmp_path):
        f = tmp_path / "bl.json"
        save_backlash_deg(5.0, f)          # 超上限 → 夹到 1.0
        assert load_backlash_deg(f) == BACKLASH_MAX_DEG
        save_backlash_deg(-1.0, f)         # 负 → 夹到 0
        assert load_backlash_deg(f) == 0.0

    def test_load_corrupt_returns_zero(self, tmp_path):
        f = tmp_path / "bl.json"
        f.write_text("{bad", encoding="utf-8")
        assert load_backlash_deg(f) == 0.0
