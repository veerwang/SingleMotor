# CLAUDE.md

此文件为 Claude Code 在本仓库中工作时提供指导。

## 重要：开始工作前

**请先阅读以下文件了解项目当前状态：**
1. `TODO.md` - 查看待办任务
2. `SESSION.md` - 查看上次会话进度

## 项目概述

本项目用于编写基于 RS-485 总线通讯协议（Modbus-RTU）的一体化步进电机驱动程序，实现对北京立迈胜（NiMotion）一体化步进电机的控制。

### 适用设备

- STM86 / STM57 H / STM57 V / STM42 系列 RS485 总线一体化步进电机（开环）
- SDM57 V / SDM42 系列 RS485 总线电机驱动器

### 通讯协议

- 物理层：RS-485 总线
- 协议：Modbus-RTU（单主站/多从站）
- 支持功能码：0x03（读保持寄存器）、0x04（读输入寄存器）、0x06（写单个寄存器）、0x10（写多个寄存器）

### 运行模式

- 位置模式（绝对/相对）、速度模式、原点回归模式、脉冲输入模式

### 技术文档

`documents/` 目录下存放了相关技术参考文档及其 Markdown 摘要，开发前务必参阅：

- `documents/一体化步进电机Modbus通讯手册_摘要.md` — 通讯协议、寄存器表、状态机、Modbus 报文速查
- `documents/STM系列常见问题及解决方法_摘要.md` — 27 个常见问题及解决方案
- `documents/SDM42系列485总线电机驱动器使用说明书_摘要.md` — SDM42 硬件规格、引脚配置、安装调试

## 项目管理说明

本项目采用文件驱动的项目管理方式：

- **CLAUDE.md** - 项目指导和架构说明（本文件）
- **TODO.md** - 任务跟踪和待办事项
- **SESSION.md** - 会话记录，用于跨会话延续上下文

### 工作流程

1. **开始新会话时**：先阅读 TODO.md 和 SESSION.md 了解当前状态
2. **工作过程中**：及时更新 TODO.md 中的任务状态
3. **结束会话前**：更新 SESSION.md 记录进度和下一步计划

## 当前状态

**最后更新**: 2026-02-13
**当前进度**: 项目初始化完成，技术文档 PDF 摘要已提取
**下一步**: 搭建 Python 项目基础结构，实现 Modbus-RTU 通讯基础模块

## 开发指南

### 语言与环境

- **语言**: Python
- **编码规范**: PEP 8
- **类型提示**: 所有公开函数和方法必须包含类型注解

### 常用命令

```bash
# 依赖管理（推荐使用 uv）
uv pip install -r requirements.txt
uv pip install <package>

# 或使用 pip
pip install -r requirements.txt

# 运行
python main.py

# 类型检查
mypy .

# 代码格式化
ruff format .

# 代码检查
ruff check .
```

### 代码规范

- 遵循 PEP 8 编码风格
- 使用 type hints 进行类型注解
- 模块、类、公开函数需有 docstring
- 串口通讯相关代码注意异常处理和超时机制
