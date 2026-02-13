"""模型层 error_codes.py 单元测试"""

import pytest
from nimotion.models.error_codes import (
    ERROR_CODES,
    MODBUS_EXCEPTIONS,
    get_error_text,
    get_exception_text,
)


class TestErrorCodes:
    def test_not_empty(self):
        assert len(ERROR_CODES) > 0

    def test_known_codes(self):
        assert ERROR_CODES[0x2200] == "过流保护"
        assert ERROR_CODES[0x3110] == "电源过压"
        assert ERROR_CODES[0x3120] == "电源欠压"
        assert ERROR_CODES[0x4310] == "过热报警"
        assert ERROR_CODES[0x7121] == "失速报警"

    def test_all_values_are_strings(self):
        for code, text in ERROR_CODES.items():
            assert isinstance(code, int)
            assert isinstance(text, str)
            assert len(text) > 0


class TestModbusExceptions:
    def test_not_empty(self):
        assert len(MODBUS_EXCEPTIONS) > 0

    def test_known_exceptions(self):
        assert MODBUS_EXCEPTIONS[0x01] == "非法功能码"
        assert MODBUS_EXCEPTIONS[0x02] == "非法数据地址"
        assert MODBUS_EXCEPTIONS[0x03] == "非法数据值"

    def test_codes_1_to_6(self):
        for i in range(1, 7):
            assert i in MODBUS_EXCEPTIONS


class TestGetErrorText:
    def test_known_code(self):
        assert get_error_text(0x2200) == "过流保护"

    def test_unknown_code(self):
        result = get_error_text(0x9999)
        assert "0x9999" in result.lower()
        assert "未知" in result

    def test_zero_code(self):
        result = get_error_text(0)
        assert "未知" in result


class TestGetExceptionText:
    def test_known_exception(self):
        assert get_exception_text(0x01) == "非法功能码"

    def test_unknown_exception(self):
        result = get_exception_text(0xFF)
        assert "0xff" in result.lower()
        assert "未知" in result
