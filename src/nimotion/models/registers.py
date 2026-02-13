"""
完整的寄存器定义表。
基于《NiMotion 一体化步进电机 Modbus 寄存器完整列表 (开环) Version B02》构建。
"""

from __future__ import annotations

from .types import DataType, RegisterDef, RegisterType

# 保持寄存器定义 (功能码 0x03 / 0x06 / 0x10)
HOLDING_REGISTERS: list[RegisterDef] = [
    # ── 通讯参数 ──
    RegisterDef(
        0x0000, "从站地址", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=1, max_val=247, default_val=1, restart_required=True,
    ),
    RegisterDef(
        0x0001, "波特率", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=9, default_val=5, restart_required=True,
        description="0=9.6k 1=9.6k 2=19.2k 3=38.4k 4=57.6k 5=115.2k 6=256k 7=500k 8=1M 9=1.5M",
    ),
    RegisterDef(
        0x0002, "网络数据格式", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=3, default_val=2, restart_required=True,
        description="0=8E1(偶校验) 1=8O1(奇校验) 2=8N1(无校验) 3=8N2(无校验,2停止位)",
    ),
    RegisterDef(
        0x0003, "Modbus返回等待时间", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="ms", min_val=0, max_val=10000, default_val=0,
        description="Modbus通信请求到响应的额外等待时间,即使设0也会有时间延迟",
    ),
    # ── 系统参数 ──
    RegisterDef(
        0x0008, "保存所有参数", RegisterType.HOLDING, DataType.UINT16, 1,
        writable=True, description="写 0x7376 保存; 读参数为1=支持",
    ),
    RegisterDef(
        0x000B, "恢复默认参数", RegisterType.HOLDING, DataType.UINT16, 1,
        writable=True, restart_required=True,
        description="写 0x6C64 恢复所有参数制造商默认值",
    ),
    # ── 电机电气参数 ──
    RegisterDef(
        0x000E, "电阻", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="mOhm", default_val=290, restart_required=True,
        description="电机的相电阻",
    ),
    RegisterDef(
        0x0010, "电感", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="uH", default_val=1770, restart_required=True,
        description="电机的相电感",
    ),
    RegisterDef(
        0x0012, "反应电动势系数", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="mV/Hz", default_val=46, restart_required=True,
        description="电机的反应电动势系数",
    ),
    RegisterDef(
        0x0014, "电压", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="V", default_val=24, restart_required=True,
        description="电源的电压",
    ),
    # ── 电流参数 ──
    RegisterDef(
        0x0015, "减速电流", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="mA", min_val=0, max_val=10000, default_val=1000,
        description="STM86: 0~10000mA峰值; 非STM86: 0~4000mA峰值",
    ),
    RegisterDef(
        0x0016, "怠机电流", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="mA", min_val=0, max_val=10000, default_val=500,
        description="STM86: 0~10000mA峰值; 非STM86: 0~4000mA峰值",
    ),
    RegisterDef(
        0x0017, "加速电流", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="mA", min_val=0, max_val=10000, default_val=1000,
        description="STM86: 0~10000mA峰值; 非STM86: 0~4000mA峰值",
    ),
    RegisterDef(
        0x0018, "运行电流", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="mA", min_val=0, max_val=10000, default_val=1000,
        description="STM86: 0~10000mA峰值; 非STM86: 0~4000mA峰值",
    ),
    RegisterDef(
        0x0019, "过载电流", RegisterType.HOLDING, DataType.UINT16, 1,
        unit="100mA", min_val=0, max_val=100, default_val=40,
        description="非STM86: 100mA单位,375mA~6A,范围0~60,默认40; STM86: 100mA单位,375mA~10A,范围0~100,默认80",
    ),
    # ── 运动参数 ──
    RegisterDef(
        0x001A, "细分", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=7, default_val=7,
        description="0=Full 1=Half 2=1:4 3=1:8 4=1:16 5=1:32 6=1:64 7=1:128; 非28系列:0~7, 28系列:0~4",
    ),
    RegisterDef(
        0x001F, "驱动参数", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=1,
        description="低速优化 Low speed optimization; 0=禁用 1=启用",
    ),
    # ── 输入配置 ──
    RegisterDef(
        0x002C, "输入特殊功能", RegisterType.HOLDING, DataType.UINT32, 2,
        default_val=0,
        description="4字节,0~3位=DI1,每DI占4位: 0=无动作 1=负限位 2=正限位 3=原点开关 4=立即停机 5=减速停机 6=方向(速度模式) 7=使能 8=运行/停止(速度模式); 注:脉冲输入模式仅1~2可用",
    ),
    RegisterDef(
        0x002E, "输入极性取反", RegisterType.HOLDING, DataType.UINT16, 1,
        default_val=0,
        description="8位,第0位=DI1,依次类推; 0=不取反 1=取反",
    ),
    RegisterDef(
        0x002F, "输入上拉使能", RegisterType.HOLDING, DataType.UINT16, 1,
        default_val=0,
        description="8位,第0位=DIO,依次类推; 0=无效 1=使能; 注:仅57系列有效",
    ),
    RegisterDef(
        0x0030, "输入触发方式", RegisterType.HOLDING, DataType.UINT32, 2,
        default_val=69905,
        description="4字节,0~3位=DI1,每DI占4位: 0=无效 1=上升沿 2=下降沿 3=上升/下降沿",
    ),
    # ── I/O 配置 ──
    RegisterDef(
        0x0034, "I/O端口配置", RegisterType.HOLDING, DataType.UINT16, 1,
        default_val=0,
        description="8位,第0位=DX1: 0=配置输入 1=配置输出",
    ),
    RegisterDef(
        0x0035, "故障安全输出", RegisterType.HOLDING, DataType.UINT16, 1,
        default_val=0,
        description="8位,第0位=DO1: 0=保留上次输出值 1=按故障安全预定值输出",
    ),
    RegisterDef(
        0x0036, "故障安全预定", RegisterType.HOLDING, DataType.UINT16, 1,
        default_val=0,
        description="8位,第0位=DO1: 每位值=故障安全状态预定值",
    ),
    RegisterDef(
        0x0037, "数字量输出", RegisterType.HOLDING, DataType.UINT32, 2,
        default_val=0,
        description="4字节,高16位=DO输出值,低16位=DO特殊功能值",
    ),
    # ── 运行模式 ──
    RegisterDef(
        0x0039, "运行模式", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=1, max_val=4, default_val=1,
        description="1=位置模式 2=速度模式 3=原点回归 4=脉冲输入(仅57H); 非57H:1~3, 57H:1~4",
    ),
    # ── 停机设置 ──
    RegisterDef(
        0x003A, "操作启停设置", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=1,
        description="0=无减速度停机 1=按减速度停机",
    ),
    RegisterDef(
        0x003B, "急停操作设置", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=1,
        description="0=无减速度停机 1=按减速度停机",
    ),
    RegisterDef(
        0x003C, "故障操作设置", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=0,
        description="0=无减速度停机 1=按减速度停机",
    ),
    # ── 检测参数 ──
    RegisterDef(
        0x0043, "失速检测阈值", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="100mA", min_val=0, max_val=100, default_val=80,
        description="STM86: 100mA单位,0~100,默认80; 非86: mA单位,0~4000,默认3000",
    ),
    # ── 原点/零点 ──
    RegisterDef(
        0x0047, "设置零点", RegisterType.HOLDING, DataType.UINT16, 1,
        description="写 0x535A 设置零点; 读参数=1表示支持指令",
    ),
    RegisterDef(
        0x0048, "设置原点", RegisterType.HOLDING, DataType.UINT16, 1,
        description="写 0x5348 设置原点; 读参数=1表示支持指令",
    ),
    # ── 运动控制 ──
    RegisterDef(
        0x0051, "运动控制字", RegisterType.HOLDING, DataType.UINT16, 1,
        description="参照手册第3节 Control word",
    ),
    RegisterDef(
        0x0052, "运动方向", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=0,
        description="0=反转 Reverse 1=正转 Forward",
    ),
    RegisterDef(
        0x0053, "目标位置", RegisterType.HOLDING, DataType.INT32, 2,
        unit="pulse", default_val=0,
        description="电机运动停止时的绝对位置",
    ),
    RegisterDef(
        0x0055, "目标速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s", min_val=0, max_val=15610, default_val=100,
        description="速度模式下目标速度",
    ),
    RegisterDef(
        0x0057, "位置最小值", RegisterType.HOLDING, DataType.INT32, 2,
        unit="pulse", default_val=0,
        description="软件下限,小于此值不再运动",
    ),
    RegisterDef(
        0x0059, "位置最大值", RegisterType.HOLDING, DataType.INT32, 2,
        unit="pulse", default_val=0,
        description="软件上限,大于此值不再运动",
    ),
    RegisterDef(
        0x005B, "最大速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s", min_val=0, max_val=15610, default_val=250,
        description="允许电机运行的最大速度",
    ),
    RegisterDef(
        0x005D, "最小速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s", min_val=0, max_val=1000, default_val=16,
        description="当驱动参数3=1时默认为0",
    ),
    RegisterDef(
        0x005F, "加速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s\u00b2", min_val=1, max_val=59590, default_val=1000,
        description="从当前速度到目标速度的加速率",
    ),
    RegisterDef(
        0x0061, "减速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s\u00b2", min_val=1, max_val=59590, default_val=1000,
        description="从当前速度到目标速度的减速率",
    ),
    # ── 原点回归 ──
    RegisterDef(
        0x0069, "原点偏移值", RegisterType.HOLDING, DataType.INT32, 2,
        unit="pulse", default_val=0,
    ),
    RegisterDef(
        0x006B, "原点回归方式", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=17, max_val=31, default_val=17,
        description="17~30=寻找开关方式; 31=快速回归(内部设定)",
    ),
    RegisterDef(
        0x006C, "寻找开关速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s", min_val=0, max_val=15610, default_val=100,
        description="原点回归时寻找限位/原点开关的速度",
    ),
    RegisterDef(
        0x006E, "寻找零位速度", RegisterType.HOLDING, DataType.UINT32, 2,
        unit="Step/s", min_val=0, max_val=15610, default_val=100,
        description="原点回归时寻找零点位置的速度",
    ),
    RegisterDef(
        0x0072, "零点回归", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=0,
        description="原点回归完后是否运行到零点; 0x01=启用 0x00=禁用",
    ),
    RegisterDef(
        0x0073, "清空错误存储器", RegisterType.HOLDING, DataType.UINT16, 1,
        description="发送 0x6C64 清零所有错误寄存器",
    ),
    RegisterDef(
        0x0074, "硬件自检", RegisterType.HOLDING, DataType.UINT16, 1,
        description="发送 0x7465 进行硬件自检",
    ),
    # ── 用户程序 (仅一体化电机嵌入式软件) ──
    RegisterDef(
        0x0075, "用户程序控制", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=3, default_val=0,
        description="0x00=禁止 0x01=使能 0x02=启动 0x03=停止; 仅一体化电机嵌入式软件",
    ),
    RegisterDef(
        0x0076, "用户程序状态", RegisterType.HOLDING, DataType.UINT16, 1,
        default_val=0, writable=False,
        description="只读; Bit8=上电启动 Bit4=程序运行 Bit0=程序存在; 仅一体化电机嵌入式软件",
    ),
    # ── 驱动模块参数 ──
    RegisterDef(
        0x007B, "电压电流模式", RegisterType.HOLDING, DataType.UINT16, 1,
        min_val=0, max_val=1, default_val=0, restart_required=True,
        description="仅86一体化和57驱动模块; 0x00=电压模式 0x01=电流模式",
    ),
]

# 输入寄存器定义 (功能码 0x04, 只读)
INPUT_REGISTERS: list[RegisterDef] = [
    # ── 设备信息 ──
    RegisterDef(
        0x0000, "厂商名称", RegisterType.INPUT, DataType.UINT32, 2,
        writable=False,
    ),
    RegisterDef(
        0x0002, "产品序列号", RegisterType.INPUT, DataType.UINT32, 2,
        writable=False,
    ),
    RegisterDef(
        0x0004, "硬件版本号", RegisterType.INPUT, DataType.UINT32, 2,
        writable=False,
    ),
    RegisterDef(
        0x000A, "软件版本号", RegisterType.INPUT, DataType.UINT32, 2,
        writable=False,
    ),
    RegisterDef(
        0x000C, "工作时间", RegisterType.INPUT, DataType.UINT32, 2,
        unit="h", writable=False, description="设备累积工作时间",
    ),
    # ── 驱动状态 ──
    RegisterDef(
        0x0016, "驱动电路状态", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="驱动电路的内部状态",
    ),
    RegisterDef(
        0x0017, "输入电压", RegisterType.INPUT, DataType.UINT16, 1,
        unit="V", writable=False,
    ),
    RegisterDef(
        0x0018, "数字量输入", RegisterType.INPUT, DataType.UINT32, 2,
        writable=False,
        description="高16位: DI输入值(bit20=DX2,bit19=DX1,bit18=DI3,bit17=DI2,bit16=DI1); 低16位: DI特殊功能值(bit2=原点开关,bit1=正限位开关,bit0=负限位开关)",
    ),
    # ── 运行状态 ──
    RegisterDef(
        0x001E, "当前操作模式", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="当前电机运行的运动模式",
    ),
    RegisterDef(
        0x001F, "运动状态字", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False,
        description="Bit0=启动 Bit1=使能 Bit2=运行 Bit3=故障 Bit4=电压使能 Bit5=快速停机使能 Bit6=电机无故障 Bit7=警告 Bit12: 0=运行完成,1=运行过程中",
    ),
    RegisterDef(
        0x0020, "当前运动方向", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="当前电机运行的方向",
    ),
    RegisterDef(
        0x0021, "当前显示位置", RegisterType.INPUT, DataType.INT32, 2,
        unit="pulse", writable=False, description="当前电机位置",
    ),
    RegisterDef(
        0x0023, "当前运行速度", RegisterType.INPUT, DataType.UINT32, 2,
        unit="Step/s", writable=False,
        description="显示值=当前电机运行速度\u00d710",
    ),
    RegisterDef(
        0x0025, "错误寄存器", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False,
        description="16位错误标志: Bit0=常规 Bit1=电流 Bit2=电压 Bit3=温度 Bit4=通信 Bit5=子协议 Bit6=预留 Bit7=制造商",
    ),
    RegisterDef(
        0x0026, "当前错误报警值", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="最近错误报警的错误码",
    ),
    RegisterDef(
        0x0027, "错误存储器报警个数", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="当前错误存储器列表中的报警个数(0~8)",
    ),
    # ── 历史报警 ──
    RegisterDef(
        0x0028, "历史报警1", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="错误码",
    ),
    RegisterDef(
        0x0029, "历史报警2", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="错误码",
    ),
    RegisterDef(
        0x002A, "历史报警3", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="错误码",
    ),
    RegisterDef(
        0x002B, "历史报警4", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="错误码",
    ),
    RegisterDef(
        0x002C, "历史报警5", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="错误码",
    ),
    RegisterDef(
        0x002D, "历史报警6", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="错误码",
    ),
    RegisterDef(
        0x002E, "历史报警7", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="错误码",
    ),
    RegisterDef(
        0x002F, "历史报警8", RegisterType.INPUT, DataType.UINT16, 1,
        writable=False, description="错误码",
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
