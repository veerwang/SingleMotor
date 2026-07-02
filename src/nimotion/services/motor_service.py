"""
电机业务逻辑层。
将寄存器操作封装为语义化方法，供 UI 层调用。
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from ..communication.modbus_rtu import ModbusRTU
from ..communication.worker import CommWorker
from ..models.error_codes import get_error_text, get_exception_text
from ..models.registers import get_register
from ..models.types import (
    DataType,
    FunctionCode,
    HomingConfig,
    ModbusRequest,
    ModbusResponse,
    MotorState,
    MotorStatus,
    RegisterType,
    RunMode,
)


class MotorService(QObject):
    """电机操作服务"""

    # 状态更新信号
    status_updated = pyqtSignal(object)  # MotorStatus
    param_read = pyqtSignal(int, int)  # (地址, 值)
    operation_done = pyqtSignal(bool, str)  # (成功, 消息)
    homing_config_status = pyqtSignal(str)  # 回零配置状态信息
    homing_done = pyqtSignal()  # 回零完成且 DI1 已恢复
    init_config_done = pyqtSignal(str)  # 首次连接参数校准完成

    # 首次连接期望参数: (地址, 期望值, 名称, 是否32位)
    # 寄存器单位 Step/s (全步/秒), 实际 pulses/s = Step/s × 细分数
    INIT_PARAMS: list[tuple[int, int, str, bool]] = [
        (0x001A, 4, "细分", False),          # 寄存器值4 = 细分16 (需重启生效)
        (0x005F, 2000, "加速度", True),     # 2000 Step/s² (28系列硬件上限约2000，≥3000报error3)
        (0x0061, 2000, "减速度", True),     # 2000 Step/s²
        # 最小速度(起停速度)必须 ≤ 最大速度，否则写最大速度会被拒(非法数据值)。
        # 必须排在最大速度之前先写小，再写最大速度 才能通过。
        (0x005D, 16, "最小速度", True),     # 16 Step/s (手册默认，起停速度)
        (0x005B, 600, "最大速度", True),    # 600 Step/s (×16=9600 pulses/s ≈ 393°/s转盘)
    ]

    def __init__(self, worker: CommWorker, slave_id: int = 1) -> None:
        super().__init__()
        self._worker = worker
        self._slave_id = slave_id
        self._last_state = MotorState.UNKNOWN
        self._worker.response_received.connect(self._on_response)

        # 回零配置状态机
        self._homing_config: HomingConfig | None = None
        self._homing_read_values: dict[int, int] = {}
        self._homing_phase: str = "idle"  # idle / reading / done
        self._homing_timeout = QTimer()
        self._homing_timeout.setSingleShot(True)
        self._homing_timeout.timeout.connect(self._on_homing_config_timeout)
        # 回零完成后恢复 DI1 的轮询
        self._homing_di_restore: int | None = None
        # 回零是否已真正跑起来(见过 is_running=True)，防止触发后未起转的空闲帧被误判为完成
        self._homing_seen_running = False
        # 回零 grace 兜底：启动后过了 grace 仍空闲则也判完成，覆盖"已在 home 点、
        # 再回零几乎不动/移动太短未被采到 is_running"的情况，避免 seen_running 门槛卡死
        self._homing_grace_over = False
        self._homing_grace_timer = QTimer()
        self._homing_grace_timer.setSingleShot(True)
        self._homing_grace_timer.setInterval(2000)
        self._homing_grace_timer.timeout.connect(self._on_homing_grace_over)
        # 回零使用的加减速为全局共用寄存器(0x005F/0x0061)，回零前改小、完成后恢复原值
        self._homing_accel_restore: int | None = None
        self._homing_decel_restore: int | None = None
        self._homing_poll_timer = QTimer()
        self._homing_poll_timer.setInterval(500)
        self._homing_poll_timer.timeout.connect(self._poll_homing_done)
        self.status_updated.connect(self._check_homing_running)

        # 首次连接参数校准状态机
        self._init_phase: str = "idle"  # idle / reading / done
        self._init_read_values: dict[int, int] = {}
        self._init_timeout = QTimer()
        self._init_timeout.setSingleShot(True)
        self._init_timeout.timeout.connect(self._on_init_config_timeout)

    @property
    def slave_id(self) -> int:
        return self._slave_id

    @slave_id.setter
    def slave_id(self, value: int) -> None:
        self._slave_id = value

    # -- 状态查询 --

    def refresh_status(self) -> None:
        """
        读取电机实时状态。
        一次批量读取 0x17~0x26 范围的输入寄存器（16 个），
        减少通讯次数。
        """
        req = ModbusRequest(
            slave_id=self._slave_id,
            function_code=FunctionCode.READ_INPUT,
            address=0x0017,
            count=16,  # 0x17 ~ 0x26
        )
        self._worker.send_modbus(req)

    # -- 状态机控制 --

    def startup(self) -> None:
        """无故障 -> 启动"""
        self._write_control_word(0x0006)

    def enable(self) -> None:
        """启动 -> 使能"""
        self._write_control_word(0x0007)

    def run(self) -> None:
        """使能 -> 运行"""
        self._write_control_word(0x000F)

    def stop(self) -> None:
        """运行 -> 使能（减速停机）"""
        self._write_control_word(0x0007)

    def quick_stop(self) -> None:
        """紧急停机"""
        self._write_control_word(0x0002)

    def disable(self) -> None:
        """回到无故障状态"""
        self._write_control_word(0x0000)

    def clear_fault(self) -> None:
        """清除故障"""
        self._write_control_word(0x0080)

    # -- 运动控制 --

    def move_relative(self, position: int) -> None:
        """相对位置运动。

        本驱动器相对模式的方向由 0x0052(0=反转/1=正转)决定，0x0053 只作
        正的步长幅值——写负数会被当成非法幅值而不动。因此按 position 的
        正负设置方向寄存器（正=正转/位置增大），幅值取绝对值。
        """
        direction = 1 if position >= 0 else 0
        self._write_control_word(0x0000)  # 先停机
        self._write_single(0x0039, int(RunMode.POSITION))  # 设置位置模式
        self._write_single(0x0052, direction)  # 运行方向: 正数=正转(位置增大)
        self._write_32bit(0x0053, abs(position))  # 步长幅值(必须为正)
        self._write_control_word(0x0006)  # 启动
        self._write_control_word(0x0007)  # 使能
        self._write_control_word(0x004F)  # 相对模式 + 运行
        self._write_control_word(0x005F)  # 触发新位置

    def move_absolute(self, position: int) -> None:
        """绝对位置运动"""
        self._write_control_word(0x0000)  # 先停机
        self._write_single(0x0039, int(RunMode.POSITION))  # 设置位置模式
        self._write_32bit(0x0053, position, signed=True)
        self._write_control_word(0x0006)  # 启动
        self._write_control_word(0x0007)  # 使能
        self._write_control_word(0x000F)  # 绝对模式 + 运行
        self._write_control_word(0x001F)  # 触发新位置

    def set_speed(self, speed: int, direction: int) -> None:
        """速度模式运行"""
        self._write_control_word(0x0000)  # 先停机
        self._write_single(0x0039, int(RunMode.SPEED))  # 设置速度模式
        self._write_single(0x0052, direction)
        self._write_32bit(0x0055, speed)
        self._write_control_word(0x0006)  # 启动
        self._write_control_word(0x0007)  # 使能
        self._write_control_word(0x000F)  # 运行

    def start_homing(self) -> None:
        """开始原点回归（不检查配置，直接启动）"""
        self._write_control_word(0x0006)  # 启动
        self._write_single(0x0039, int(RunMode.HOMING))  # 设置原点回归模式
        self._write_control_word(0x0006)  # 启动
        self._write_control_word(0x0007)  # 使能
        self._write_control_word(0x000F)  # 运行
        self._write_control_word(0x001F)  # 触发
        # 如果需要回零后恢复 DI1，启动轮询
        if self._homing_di_restore is not None:
            self._homing_poll_timer.start()

    def configure_and_start_homing(self, config: HomingConfig) -> None:
        """先确保设备回零参数与期望一致，再启动回零。

        流程：读取设备当前值 → 比对 → 仅写差异 → 有写入才保存 EEPROM → 启动回零。
        """
        if self._homing_phase != "idle":
            self.operation_done.emit(False, "回零配置流程进行中，请稍候")
            return
        self._homing_config = config
        self._homing_read_values.clear()
        self._homing_phase = "reading"
        self._homing_timeout.start(3000)
        # 发起 6 次读取
        self.read_param(0x002C, 2)   # DI功能 (2 reg, UINT32)
        self.read_param(0x006B, 1)   # 回归方式 (1 reg)
        self.read_param(0x0069, 2)   # 原点偏移 (2 reg, INT32)
        self.read_param(0x006C, 2)   # 寻找开关速度 (2 reg, UINT32)
        self.read_param(0x006E, 2)   # 寻找零位速度 (2 reg, UINT32)
        self.read_param(0x005F, 2)   # 加速度 (2 reg, UINT32) - 回零前改小，完成后恢复
        self.read_param(0x0061, 2)   # 减速度 (2 reg, UINT32) - 回零前改小，完成后恢复
        self.read_param(0x0072, 1)   # 零点回归 (1 reg)

    # -- 首次连接参数校准 --

    def check_init_params(self) -> None:
        """首次连接时读取关键参数，与期望值比对，不一致则写入。"""
        if self._init_phase != "idle":
            return
        self._init_phase = "reading"
        self._init_read_values.clear()
        self._init_timeout.start(3000)
        for addr, _val, _name, is_32bit in self.INIT_PARAMS:
            self.read_param(addr, 2 if is_32bit else 1)

    def _check_init_reads_complete(self) -> None:
        """检查初始化参数是否全部读取完毕"""
        needed = {addr for addr, _, _, _ in self.INIT_PARAMS}
        if not needed.issubset(self._init_read_values):
            return
        self._init_timeout.stop()
        self._init_phase = "done"

        diffs: list[str] = []
        for addr, expected, name, is_32bit in self.INIT_PARAMS:
            current = self._init_read_values[addr]
            if current != expected:
                if is_32bit:
                    self._write_32bit(addr, expected)
                else:
                    self._write_single(addr, expected)
                diffs.append(f"{name} {current}->{expected}")

        if diffs:
            self.save_params()
            msg = "参数已校准并保存: " + ", ".join(diffs)
        else:
            msg = "参数检查通过，无需校准"
        self._init_phase = "idle"
        self.init_config_done.emit(msg)

    def _on_init_config_timeout(self) -> None:
        """首次校准读取超时"""
        self._init_phase = "idle"
        self.init_config_done.emit("参数校准超时，跳过")

    # -- 参数操作 --

    def read_param(self, address: int, count: int = 1) -> None:
        """读取保持寄存器"""
        req = ModbusRequest(
            slave_id=self._slave_id,
            function_code=FunctionCode.READ_HOLDING,
            address=address,
            count=count,
        )
        self._worker.send_modbus(req)

    def write_param(self, address: int, value: int) -> None:
        """写入单个保持寄存器"""
        self._write_single(address, value)

    def write_param_32bit(
        self, address: int, value: int, signed: bool = False
    ) -> None:
        """写入 32 位参数（2 个寄存器）"""
        self._write_32bit(address, value, signed)

    def save_params(self) -> None:
        """保存所有参数到 EEPROM"""
        self._write_single(0x0008, 0x7376)

    def restore_defaults(self) -> None:
        """恢复出厂默认参数"""
        self._write_single(0x000B, 0x6C64)

    def set_run_mode(self, mode: RunMode) -> None:
        """设置运行模式"""
        self._write_single(0x0039, int(mode))

    def set_origin(self) -> None:
        """设置原点"""
        self._write_single(0x0048, 0x5348)

    def set_zero(self) -> None:
        """设置零点"""
        self._write_single(0x0047, 0x535A)

    # -- 内部方法 --

    def _ensure_enabled(self) -> None:
        """确保电机至少处于使能状态，按需补发启动/使能命令。

        根据缓存的状态判断：
        - 已使能/运行：无需操作
        - 已启动：只需发使能(0x07)
        - 其他(无故障/未知等)：发启动(0x06)+使能(0x07)
        """
        if self._last_state in (
            MotorState.SWITCHED_ON,
            MotorState.OPERATION_ENABLED,
        ):
            return
        if self._last_state == MotorState.READY_TO_SWITCH_ON:
            self._write_control_word(0x0007)
        else:
            self._write_control_word(0x0006)
            self._write_control_word(0x0007)

    def _write_control_word(self, value: int) -> None:
        self._write_single(0x0051, value)

    def _write_single(self, address: int, value: int) -> None:
        req = ModbusRequest(
            slave_id=self._slave_id,
            function_code=FunctionCode.WRITE_SINGLE,
            address=address,
            values=[value & 0xFFFF],
        )
        self._worker.send_modbus(req)

    def _write_32bit(
        self, address: int, value: int, signed: bool = False
    ) -> None:
        high, low = ModbusRTU.split_32bit(value)
        req = ModbusRequest(
            slave_id=self._slave_id,
            function_code=FunctionCode.WRITE_MULTIPLE,
            address=address,
            count=2,
            values=[high, low],
        )
        self._worker.send_modbus(req)

    def _on_response(self, resp: ModbusResponse) -> None:
        """处理通讯线程返回的响应"""
        if resp.is_error:
            self.operation_done.emit(False, self._format_error(resp))
            return

        # 判断是状态查询响应还是参数响应
        if resp.function_code == FunctionCode.READ_INPUT:
            self._parse_status(resp)
        elif resp.function_code == FunctionCode.READ_HOLDING:
            if not resp.raw_tx or len(resp.raw_tx) < 4:
                return
            start_addr = (resp.raw_tx[2] << 8) | resp.raw_tx[3]
            values = resp.values
            # 检查是否为 32 位寄存器读取（2 个寄存器）
            reg = get_register(start_addr, RegisterType.HOLDING)
            if (
                reg
                and reg.data_type in (DataType.UINT32, DataType.INT32)
                and len(values) == 2
            ):
                signed = reg.data_type == DataType.INT32
                combined = ModbusRTU.combine_32bit(values[0], values[1], signed)
                self.param_read.emit(start_addr, combined)
                if self._homing_phase == "reading":
                    self._homing_read_values[start_addr] = combined
            else:
                for i, val in enumerate(values):
                    self.param_read.emit(start_addr + i, val)
                    if self._homing_phase == "reading":
                        self._homing_read_values[start_addr + i] = val
            if self._homing_phase == "reading":
                self._check_homing_reads_complete()
            if self._init_phase == "reading":
                if (
                    reg
                    and reg.data_type in (DataType.UINT32, DataType.INT32)
                    and len(values) == 2
                ):
                    signed = reg.data_type == DataType.INT32
                    self._init_read_values[start_addr] = ModbusRTU.combine_32bit(
                        values[0], values[1], signed,
                    )
                else:
                    for i, val in enumerate(values):
                        self._init_read_values[start_addr + i] = val
                self._check_init_reads_complete()
        else:
            self.operation_done.emit(True, "操作成功")

    def _parse_status(self, resp: ModbusResponse) -> None:
        """从批量读取结果中解析电机状态"""
        vals = resp.values
        if len(vals) < 16:
            return

        # 偏移量基于起始地址 0x17
        status = MotorStatus()
        status.voltage = vals[0]  # 0x17
        # vals[1], vals[2] = 0x18~0x19 (DI, 32位)
        # vals[3]~vals[6] = 0x1A~0x1D (预留)
        # vals[7] = 0x1E (当前模式)
        status.current_mode = RunMode(vals[7]) if vals[7] in (1, 2, 3, 4) else None
        # vals[8] = 0x1F (状态字)
        status.status_word = vals[8]
        status.state = self._decode_state(vals[8])
        status.is_running = bool(vals[8] & (1 << 12))
        # vals[1] = 0x18 高16位 = DI 原始电平 (bit0=DI1)
        status.di_status = vals[1]
        # vals[9] = 0x20 (方向)
        status.direction = vals[9]
        # vals[10], vals[11] = 0x21~0x22 (位置, 32位)
        status.position = ModbusRTU.combine_32bit(vals[10], vals[11], signed=True)
        # vals[12], vals[13] = 0x23~0x24 (速度, 32位, 值=实际x10)
        raw_speed = ModbusRTU.combine_32bit(vals[12], vals[13])
        status.speed = raw_speed // 10
        # vals[14] = 0x25 (错误寄存器)
        # vals[15] = 0x26 (当前报警码)
        status.alarm_code = vals[15]
        status.alarm_text = get_error_text(vals[15]) if vals[15] else ""

        self._last_state = status.state
        self.status_updated.emit(status)

    @staticmethod
    def _decode_state(word: int) -> MotorState:
        """从状态字解码电机状态"""
        if word & 0x0008:  # bit3 = 故障
            return MotorState.FAULT
        if word == 0x0050:
            return MotorState.SWITCH_ON_DISABLED
        if word == 0x0031:
            return MotorState.READY_TO_SWITCH_ON
        if word == 0x0033:
            return MotorState.SWITCHED_ON
        if word == 0x0037:
            return MotorState.OPERATION_ENABLED
        if word == 0x0017:
            return MotorState.QUICK_STOP
        return MotorState.UNKNOWN

    def _check_homing_reads_complete(self) -> None:
        """检查回零配置参数是否全部读取完毕"""
        needed = {0x002C, 0x0069, 0x006B, 0x005F, 0x0061, 0x006C, 0x006E, 0x0072}
        if not needed.issubset(self._homing_read_values):
            return
        self._homing_timeout.stop()
        self._homing_phase = "idle"
        config = self._homing_config
        assert config is not None

        # 先停机，确保参数可写入
        self._write_control_word(0x0000)

        # 比对设备值与期望值
        # 0x002C: DI功能，DI1占bit[3:0]，回零时强制负限位
        dev_di_func = self._homing_read_values[0x002C]
        dev_di1 = dev_di_func & 0x0F
        dev_method = self._homing_read_values[0x006B]
        # 32位寄存器已在 _on_response 中合并存储
        dev_offset = self._homing_read_values[0x0069]
        dev_search_speed = self._homing_read_values[0x006C]
        dev_zero_speed = self._homing_read_values[0x006E]
        dev_accel = self._homing_read_values[0x005F]
        dev_decel = self._homing_read_values[0x0061]
        dev_zero_ret = self._homing_read_values[0x0072]

        diffs: list[str] = []
        # 回零时强制 DI1=neg_limit(1)，method 17 依赖负限位信号
        if dev_di1 != 1:
            new_di_func = (dev_di_func & ~0x0F) | 1
            self._write_32bit(0x002C, new_di_func)
            diffs.append(f"DI1功能 {dev_di1}->1(负限位)")
        if dev_method != config.method:
            self._write_single(0x006B, config.method)
            diffs.append(f"回归方式 {dev_method}->{config.method}")
        if dev_offset != config.origin_offset:
            self._write_32bit(0x0069, config.origin_offset, signed=True)
            diffs.append(f"原点偏移 {dev_offset}->{config.origin_offset}")
        if dev_search_speed != config.search_speed:
            self._write_32bit(0x006C, config.search_speed)
            diffs.append(f"寻找开关速度 {dev_search_speed}->{config.search_speed}")
        if dev_zero_speed != config.zero_speed:
            self._write_32bit(0x006E, config.zero_speed)
            diffs.append(f"寻找零位速度 {dev_zero_speed}->{config.zero_speed}")
        # 回零加减速改小以提升重复定位精度；记录原值，回零完成后恢复(避免影响转盘定位)
        if dev_accel != config.accel:
            self._write_32bit(0x005F, config.accel)
            diffs.append(f"回零加速度 {dev_accel}->{config.accel}")
        if dev_decel != config.decel:
            self._write_32bit(0x0061, config.decel)
            diffs.append(f"回零减速度 {dev_decel}->{config.decel}")
        self._homing_accel_restore = dev_accel
        self._homing_decel_restore = dev_decel
        if dev_zero_ret != config.zero_return:
            self._write_single(0x0072, config.zero_return)
            diffs.append(f"零点回归 {dev_zero_ret}->{config.zero_return}")

        if diffs:
            # 不写 EEPROM：回零参数每次回零都先读后写重新应用(立即生效)，无需持久化；
            # 且 DI1/加减速是临时值(回零后在 _check_homing_running 恢复原值)，若存 EEPROM
            # 会把加减速永久写成回零小值(断电后转盘定位变慢)，并且每次回零都磨损 EEPROM。
            msg = "已更新: " + ", ".join(diffs)
            self.homing_config_status.emit(msg)
        else:
            self.homing_config_status.emit("参数已一致，无需写入")

        # 启动回零；完成后通过 status_updated 监测状态字恢复 DI1
        self._homing_di_restore = dev_di_func  # 记录原始 DI 配置
        self._homing_seen_running = False  # 等回零真正跑起来再判定完成
        self._homing_grace_over = False    # grace 兜底(已在 home 点再回零)
        self._homing_grace_timer.start()
        self.start_homing()

    def _poll_homing_done(self) -> None:
        """轮询回零是否完成，完成后恢复 DI1 为无动作(0)"""
        self.refresh_status()

    def _on_homing_grace_over(self) -> None:
        """回零 grace 到期：即使未采到 is_running=True 也允许判完成(已在 home 点场景)。"""
        self._homing_grace_over = True
        self.refresh_status()  # 立即取一帧推进判定

    def _check_homing_running(self, status: MotorStatus) -> None:
        """由 status_updated 信号触发，检测回零完成"""
        if self._homing_di_restore is None:
            return
        # 必须先看到"运行中"，才认可之后的"停止"为回零完成；否则触发回零后电机尚未
        # 起转的空闲帧(is_running=False)会被误判为立即完成(表现为第一次回零秒返回成功、
        # 实际没动，第二次才真回零)。grace 兜底覆盖"已在 home 点、再回零几乎不动"的情况：
        # 过了 grace(2s)仍空闲则也判完成，避免门槛卡死。
        if status.is_running:
            self._homing_seen_running = True
            return
        if (self._homing_seen_running or self._homing_grace_over) and status.speed == 0:
            self._homing_grace_timer.stop()
            self._homing_poll_timer.stop()
            # 先停机，避免写 DI 时 error=6 (slave busy)
            self._write_control_word(0x0000)
            # 恢复 DI1 为无动作(0)，保留其他 DI 配置
            restore = (self._homing_di_restore & ~0x0F) | 0
            self._write_32bit(0x002C, restore)
            self._homing_di_restore = None
            # 恢复回零前改小的加减速为原值(0x005F/0x0061 全局共用，避免拖慢转盘定位)
            msg = "回零完成，DI1 已恢复为无动作"
            if self._homing_accel_restore is not None:
                self._write_32bit(0x005F, self._homing_accel_restore)
                self._write_32bit(0x0061, self._homing_decel_restore)
                msg += f"，加减速已恢复为 {self._homing_accel_restore}"
                self._homing_accel_restore = None
                self._homing_decel_restore = None
            # 回零后保持使能并夹持力矩：上面为改 DI 写了 0x0000(脱机)。实测该驱动器
            # 仅 Operation Enabled(0x000F/0x0037) 才施加保持电流夹住电机，Switched On
            # (0x0007) 不夹持。这里从脱机态重新上电到 0x000F 保持力矩、停在 home。
            # 先切位置模式，避免在回零模式下 operation-enabled 的语义歧义；0x000F 不含
            # 新位置触发位，位置模式下不会产生运动，也不会重新回零。
            self._write_single(0x0039, int(RunMode.POSITION))  # 位置模式
            self._write_control_word(0x0006)  # 就绪
            self._write_control_word(0x0007)  # 使能
            self._write_control_word(0x000F)  # 运行使能(保持力矩夹持)
            msg += "，电机保持使能夹持"
            self.homing_config_status.emit(msg)
            self.homing_done.emit()

    def _on_homing_config_timeout(self) -> None:
        """回零配置读取超时"""
        self._homing_phase = "idle"
        self.operation_done.emit(False, "读取回零参数超时")

    @staticmethod
    def _format_error(resp: ModbusResponse) -> str:
        if resp.error_code == -1:
            return "CRC 校验失败"
        if resp.error_code == -2:
            return "通讯超时"
        if resp.error_code == -3:
            return "响应帧不完整"
        # 附带触发异常的功能码与寄存器地址，便于定位是哪条报文被拒
        detail = ""
        if len(resp.raw_tx) >= 4:
            func = resp.raw_tx[1]
            addr = (resp.raw_tx[2] << 8) | resp.raw_tx[3]
            detail = f" [功能码 0x{func:02X} 地址 0x{addr:04X}]"
        return f"Modbus 异常: {get_exception_text(resp.error_code)}{detail}"
