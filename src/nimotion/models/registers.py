"""
完整的寄存器定义表。
基于《一体化步进电机 Modbus 通讯用户手册（开环）B02》构建。
"""

from __future__ import annotations

from .types import DataType, RegisterDef, RegisterType

# 保持寄存器定义
HOLDING_REGISTERS: list[RegisterDef] = [
    RegisterDef(
        0x0000, "从站地址", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=1, max_val=247, default_val=1, restart_required=True,
    ),
    RegisterDef(
        0x0001, "波特率", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=9, default_val=5, restart_required=True,
        description="0=9.6k 2=19.2k 3=38.4k 4=57.6k 5=115.2k 6=256k 7=500k 8=1M",
    ),
    RegisterDef(
        0x0002, "网络数据格式", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=3, default_val=2, restart_required=True,
        description="0=偶校验 1=奇校验 2=无校验1停止 3=无校验2停止",
    ),
    RegisterDef(
        0x0008, "保存所有参数", RegisterType.HOLDING, DataType.UINT16, 1,
        writable=True, description="写 0x7376",
    ),
    RegisterDef(
        0x000B, "恢复默认参数", RegisterType.HOLDING, DataType.UINT16, 1,
        writable=True, restart_required=True, description="写 0x6C64",
    ),
    RegisterDef(
        0x0015, "减速电流", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="mA", min_val=0, max_val=10000, default_val=1000,
    ),
    RegisterDef(
        0x0016, "怠机电流", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="mA", min_val=0, max_val=10000, default_val=500,
    ),
    RegisterDef(
        0x0017, "加速电流", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="mA", min_val=0, max_val=10000, default_val=1000,
    ),
    RegisterDef(
        0x0018, "运行电流", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="mA", min_val=0, max_val=10000, default_val=1000,
    ),
    RegisterDef(
        0x0019, "过载电流", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="100mA", min_val=0, max_val=100, default_val=40,
    ),
    RegisterDef(
        0x001A, "细分", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=7, default_val=7,
        description="0=Full 1=Half 2=1:4 3=1:8 4=1:16 5=1:32 6=1:64 7=1:128",
    ),
    RegisterDef(
        0x0039, "运行模式", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=1, max_val=4, default_val=1,
        description="1=位置 2=速度 3=原点回归 4=脉冲输入(仅57H)",
    ),
    RegisterDef(
        0x003A, "操作启停设置", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=1, description="0=无减速 1=减速停机",
    ),
    RegisterDef(
        0x003B, "急停操作设置", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=1,
    ),
    RegisterDef(
        0x003C, "故障操作设置", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=0,
    ),
    RegisterDef(
        0x0043, "失速检测阈值", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="100mA", min_val=0, max_val=100, default_val=80,
    ),
    RegisterDef(
        0x0047, "设置零点", RegisterType.HOLDING, DataType.UINT16, 1,
        description="写 0x535A",
    ),
    RegisterDef(
        0x0048, "设置原点", RegisterType.HOLDING, DataType.UINT16, 1,
        description="写 0x5348",
    ),
    RegisterDef(
        0x0051, "运动控制字", RegisterType.HOLDING, DataType.UINT16, 1,
    ),
    RegisterDef(
        0x0052, "运动方向", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=0, description="0=反转 1=正转",
    ),
    RegisterDef(
        0x0053, "目标位置", RegisterType.HOLDING, DataType.INT32, 2,
        unit="pulse", default_val=0,
    ),
    RegisterDef(
        0x0055, "目标速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s", min_val=0, max_val=15610, default_val=100,
    ),
    RegisterDef(
        0x0057, "位置最小值", RegisterType.HOLDING, DataType.INT32, 2,
        unit="pulse", default_val=0,
    ),
    RegisterDef(
        0x0059, "位置最大值", RegisterType.HOLDING, DataType.INT32, 2,
        unit="pulse", default_val=0,
    ),
    RegisterDef(
        0x005B, "最大速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s", min_val=0, max_val=15610, default_val=250,
    ),
    RegisterDef(
        0x005D, "最小速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s", min_val=0, max_val=1000, default_val=16,
    ),
    RegisterDef(
        0x005F, "加速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s\u00b2", min_val=1, max_val=59590, default_val=1000,
    ),
    RegisterDef(
        0x0061, "减速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s\u00b2", min_val=1, max_val=59590, default_val=1000,
    ),
    RegisterDef(
        0x0069, "原点偏移值", RegisterType.HOLDING, DataType.INT32, 2,
        unit="pulse", default_val=0,
    ),
    RegisterDef(
        0x006B, "原点回归方式", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=17, max_val=31, default_val=17,
    ),
    RegisterDef(
        0x006C, "寻找开关速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s", min_val=0, max_val=15610, default_val=100,
    ),
    RegisterDef(
        0x006E, "寻找零位速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s", min_val=0, max_val=15610, default_val=100,
    ),
    RegisterDef(
        0x0072, "零点回归", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=0,
    ),
    RegisterDef(
        0x0073, "清空错误存储器", RegisterType.HOLDING, DataType.UINT16, 1,
        description="写 0x6C64",
    ),
]

# 输入寄存器定义
INPUT_REGISTERS: list[RegisterDef] = [
    RegisterDef(
        0x0017, "输入电压", RegisterType.INPUT, DataType.UINT16, 1,
        unit="V", writable=False,
    ),
    RegisterDef(
        0x0018, "数字量输入", RegisterType.INPUT, DataType.UINT32, 2,
        writable=False,
    ),
    RegisterDef(
        0x001E, "当前操作模式", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False,
    ),
    RegisterDef(
        0x001F, "运动状态字", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False,
    ),
    RegisterDef(
        0x0020, "当前运动方向", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False,
    ),
    RegisterDef(
        0x0021, "当前显示位置", RegisterType.INPUT, DataType.INT32, 2,
        unit="pulse", writable=False,
    ),
    RegisterDef(
        0x0023, "当前运行速度", RegisterType.INPUT, DataType.UINT32, 2,
        unit="Step/s", writable=False, description="显示值=实际\u00d710",
    ),
    RegisterDef(
        0x0025, "错误寄存器", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False,
    ),
    RegisterDef(
        0x0026, "当前错误报警值", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False,
    ),
    RegisterDef(
        0x0027, "错误存储器报警个数", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False,
    ),
]

# 索引：按地址快速查找
_HOLDING_MAP: dict[int, RegisterDef] = {r.address: r for r in HOLDING_REGISTERS}
_INPUT_MAP: dict[int, RegisterDef] = {r.address: r for r in INPUT_REGISTERS}


def get_register(address: int, reg_type: RegisterType) -> RegisterDef | None:
    """按地址和类型查找寄存器定义"""
    if reg_type == RegisterType.HOLDING:
        return _HOLDING_MAP.get(address)
    return _INPUT_MAP.get(address)
