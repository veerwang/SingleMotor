"""物镜转盘模型单元测试"""

import pytest
from nimotion.models.turret import (
    GEAR_RATIO,
    MOTOR_PULSES_PER_REV,
    POSITION_PULSES,
    POSITION_TOLERANCE,
    PULSES_PER_POSITION,
    TurretPosition,
    pulse_to_turret_position,
)


class TestConstants:
    def test_gear_ratio(self):
        assert GEAR_RATIO == 2.75

    def test_motor_pulses_per_rev(self):
        assert MOTOR_PULSES_PER_REV == 25600

    def test_pulses_per_position(self):
        assert PULSES_PER_POSITION == 17600

    def test_position_tolerance(self):
        assert POSITION_TOLERANCE == 50


class TestTurretPosition:
    def test_values(self):
        assert TurretPosition.UNKNOWN == -1
        assert TurretPosition.POS_1 == 0
        assert TurretPosition.POS_2 == 1
        assert TurretPosition.POS_3 == 2
        assert TurretPosition.POS_4 == 3

    def test_count(self):
        assert len(TurretPosition) == 5


class TestPositionPulses:
    def test_position_pulse_values(self):
        assert POSITION_PULSES[TurretPosition.POS_1] == 0
        assert POSITION_PULSES[TurretPosition.POS_2] == 17600
        assert POSITION_PULSES[TurretPosition.POS_3] == 35200
        assert POSITION_PULSES[TurretPosition.POS_4] == 52800

    def test_all_positions_mapped(self):
        for pos in TurretPosition:
            if pos != TurretPosition.UNKNOWN:
                assert pos in POSITION_PULSES

    def test_unknown_not_in_map(self):
        assert TurretPosition.UNKNOWN not in POSITION_PULSES


class TestPulseToTurretPosition:
    def test_exact_positions(self):
        assert pulse_to_turret_position(0) == TurretPosition.POS_1
        assert pulse_to_turret_position(17600) == TurretPosition.POS_2
        assert pulse_to_turret_position(35200) == TurretPosition.POS_3
        assert pulse_to_turret_position(52800) == TurretPosition.POS_4

    def test_within_tolerance(self):
        assert pulse_to_turret_position(50) == TurretPosition.POS_1
        assert pulse_to_turret_position(-50) == TurretPosition.POS_1
        assert pulse_to_turret_position(17600 + 49) == TurretPosition.POS_2
        assert pulse_to_turret_position(17600 - 50) == TurretPosition.POS_2
        assert pulse_to_turret_position(35200 + 30) == TurretPosition.POS_3
        assert pulse_to_turret_position(52800 - 1) == TurretPosition.POS_4

    def test_outside_tolerance(self):
        assert pulse_to_turret_position(51) == TurretPosition.UNKNOWN
        assert pulse_to_turret_position(-51) == TurretPosition.UNKNOWN
        assert pulse_to_turret_position(17600 + 51) == TurretPosition.UNKNOWN
        assert pulse_to_turret_position(8800) == TurretPosition.UNKNOWN

    def test_boundary_exact(self):
        """容差边界精确测试: ±50 内匹配，±51 不匹配。"""
        for pos, target in POSITION_PULSES.items():
            assert pulse_to_turret_position(target + 50) == pos
            assert pulse_to_turret_position(target - 50) == pos
            assert pulse_to_turret_position(target + 51) == TurretPosition.UNKNOWN
            assert pulse_to_turret_position(target - 51) == TurretPosition.UNKNOWN

    def test_large_offset(self):
        assert pulse_to_turret_position(100000) == TurretPosition.UNKNOWN
        assert pulse_to_turret_position(-100000) == TurretPosition.UNKNOWN
