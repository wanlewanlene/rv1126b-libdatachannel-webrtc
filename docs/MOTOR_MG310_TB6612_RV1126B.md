# MG310 编码电机 + TB6612 驱动：例程整理与 RV1126B 移植笔记

整理日期：2026-09-12。来源：WHEELTEC 两份 STM32 例程 + TB6612 模块手册/原理图 + ELF-RV1126B 手册与引脚复用表。

## 一、STM32 例程整理

### 例程 1（单路编码器读数）：STM32F103_Encoder_demo

编码器接 PB6/PB7，TIM4 用编码器接口模式 3（TI12，A/B 双边沿 4 倍频），IC 滤波=10，ARR=0xFFFF。
读法：`Encoder_TIM=TIM4->CNT;` 若 >0xefff 则减 0xFFFF 转为有符号（正=正转），读完清零 CNT。主循环每 200ms 打印一次——"单位时间内的计数差"即速度。

> 注意：该工程目录下 `STM32例程对应接线说明.txt` 写的是"D103A 单路例程"的接法（PWMA→B6、AIN1→B8、AIN2→B7、STBY→5V），与编码器例程的 PB6/PB7 冲突，实际以工程代码为准。

### 例程 2（双电机闭环）：D153Bdemo（霍尔编码器）

目录：`HAREWER\{GPIO,MOTO,PWM,ENCODER,TIMER,ADC}`，`USER\main.c`

各模块职责：

- `gpio.c`：AIN1/AIN2/BIN1/BIN2 方向脚初始化（PB12~PB15 推挽输出）
- `pwm.c`：TIM3 CH3/CH4 → PB0(PWMB)/PB1(PWMA)，10kHz；`Set_PWM(PWMA,PWMB)` 按符号设方向+PWM（±7200 满转）
- `encoder.c`：A 电机 TIM4(PB6/PB7)、B 电机 TIM2(PA0/PA1)，均编码器模式 3；`Read_Encoder(4/2)` 读后清零
- `timer.c`：TIM1 定时 10ms 中断——读双编码器 →（开环给 3000，或闭环走 PI）→ `Set_PWM()`；每 1s 串口打印
- `moto.c`：增量式 PI 速度环 `Velocity_A/B()`，Kp=1、Ki=3，输出限幅 ±7200
- `adc.c`：PA6 采集电池电压（1/11 分压）

**D153B ↔ STM32F103C8T6 接线（官方表 4-2-1）**

| D153B | STM32 | 说明 |
| --- | --- | --- |
| PWMA / AIN1 / AIN2 | PB1 / PB14 / PB15 | A 电机 PWM+方向 |
| PWMB / BIN1 / BIN2 | PB0 / PB13 / PB12 | B 电机 PWM+方向 |
| STBY | 3.3V | 常使能 |
| E1A / E1B | PB6 / PB7 | A 电机编码器 A/B 相（TIM4） |
| E2A / E2B | PA0 / PA1 | B 电机编码器 A/B 相（TIM2） |
| ADC | PA6 | 电池电压检测（可选） |
| VM | 5~15V 外接电源 | 电机功率电源 |
| 5V / GND1 | 5V / GND | 逻辑电源/共地；GND2 接外接电源地 |

## 二、TB6612 关键参数与真值表

- VM 4.5~13.5V（电机电源），VCC 2.7~5.5V（逻辑电源），Iout 1.2A 平均 / 3.2A 峰值
- PWM 频率 0~100kHz，推荐 10kHz；STBY=1 工作、=0 待机（D153B 上直接接 3.3V）

**真值表**

| PWM | IN1 | IN2 | 功能 |
| --- | --- | --- | --- |
| 1 | 0 | 0 | 制动停止 |
| 1 | 1 | 0 | 正转 |
| 1 | 0 | 1 | 反转 |
| 1 | 1 | 1 | 制动停止 |
| 0 | x | x | 停止（滑行） |

> 只给 IN1/IN2 不给 PWM 时电机不转（必须有 PWM 才有输出）。PWM=0 时是"滑行停止"，IN1=IN2=1 是"刹车"。

**D153B 模块排针（据原理图）**

- Input_IO（H1，7pin）：PWMB / BIN2 / BIN1 / STBY / AIN1 / AIN2 / PWMA
- Output_IO（H2，7pin）：E2B / E2A / E1B / E1A / ADC / GND / 5V
- 电机 6PIN 接口（Motor_A）：1=GND、2=AOUT1、3=E1A、4=E1B、5=AOUT2、6=5V
  - Motor_B 同构：2=BOUT1、3=E2A、4=E2B、5=BOUT2（1/6 同为 GND/5V）

### MG310 电机侧 6PIN 线序（官方线序图）

| 引脚 | 定义 | 颜色（手册图注） |
| --- | --- | --- |
| 1 | 电机线 − | 棕线 |
| 2 | 编码器电源（3.3~5V） | 红线 |
| 3 | 编码器输出 A 相 | 绿线（部分资料标注为 B 相） |
| 4 | 编码器输出 B 相 | 白线（部分资料标注为 A 相） |
| 5 | 编码器地线 | 黑线 |
| 6 | 电机线 + | 黄线 |

> 编码器 A/B 相颜色在两份资料中标注不一致；接反只会导致计数方向相反，软件取负号即可，不必改硬件。
> 编码器需供电才能输出：输出高电平 = 编码器供电电压；可用万用表测"GND 与 AB 相"在转动时约为 1.6~1.8V 摆动来判断好坏。

### 编码器测速公式

`速度 = 单位时间计数差 × 读取频率 / 倍频数 / 减速比 / 编码器线数 × 轮周长`

- 倍频数：STM32 例程用 4（编码器模式 3 双边沿）
- MG310 编码器线数/减速比以电机铭牌为准（常见 13 线/圈 × 减速比）

## 三、RV1126B 侧 GPIO 调用方法（手册 3.1.11 GPIO 命令行测试）

- 电平 0~3.3V，严禁接入超过 3.3V 的信号
- 命名 `GPIOn_xy`，x∈{A,B,C,D} 对应 1~4；编号公式：

  `编号 = n × 32 + (组序号−1) × 8 + y`，例：GPIO5_A6 = 5×32 + 0×8 + 6 = 166

- 输出模式：

```bash
echo 166 > /sys/class/gpio/export
echo out > /sys/class/gpio/gpio166/direction
echo 1   > /sys/class/gpio/gpio166/value
echo 0   > /sys/class/gpio/gpio166/value
echo 166 > /sys/class/gpio/unexport
```

- 输入模式：

```bash
echo 166 > /sys/class/gpio/export
echo in  > /sys/class/gpio/gpio166/direction
cat /sys/class/gpio/gpio166/value
echo 166 > /sys/class/gpio/unexport
```

> 亦可使用 libgpiod（`gpioset/gpioget/gpiomon`）或 sysfs `edge` + `poll()`；`edge` 支持 `none/rising/falling/both`，编码器计数建议用 `both` 边沿。

## 四、RV1126B 引脚候选（据"FET1126B-S 引脚复用表"）

选型原则：电机方向脚用任意 GPIO（输出，3.3V）；PWMA/PWMB 用 PWM 通道脚；编码器 A/B 相用普通 GPIO（需支持中断/边沿）。

**可用 PWM 通道（复用表中列出）**

| PWM 通道 | 引脚 | 编号(GPIO n_xy 换算) |
| --- | --- | --- |
| PWM3_CH0~7_M1 | GPIO5_C0~C7 | 176~183 |
| PWM0_CH2~3_M0 | GPIO0_C6/C7 | 198 / 199 |
| PWM1_CH2~3_M0 | GPIO0_B3/B4 | 131 / 132（默认为调试串口 UART0） |
| PWM2_CH0~3_M1 | GPIO5_B2~B5 | 146~149 |
| PWM0_CH0~1_M1 | GPIO5_A7/A6 | 127 / 126 |
| PWM2_CH4~7_M1 | GPIO7_A0~A3 | 224~227 |
| PWM0_CH4~5_M0 | GPIO0_D0/D1 | 200 / 201 |
| PWM0_CH6~7_M1 | GPIO4_A6/A7 | 118 / 119 |

**首选组合建议（两路电机刚好够用）**

- PWMA=PWM3_CH0(GPIO5_C0/176)、PWMB=PWM3_CH1(GPIO5_C1/177)
- 方向：AIN1/AIN2/BIN1/BIN2 用 GPIO5_C2~C5（178~181，与 PWM 同组，接线集中）
- 编码器输入：E1A/E1B = GPIO5_C6/C7（182/183），E2A/E2B = GPIO5_D0/D1（184/185）
- STBY 直接接模块 3V3，无需占 GPIO

> 待确认：上述引脚是否已被底板占用（WiFi/BT、MIPI、Flash 等），接线前请对照复用表"开发板引脚功能"列确认。

## 五、移植方案（STM32 → Linux）

### 5.1 硬件映射（建议）

| D153B | RV1126B | 编号 |
| --- | --- | --- |
| PWMA | GPIO5_C0 | 176（PWM3_CH0） |
| PWMB | GPIO5_C1 | 177（PWM3_CH1） |
| AIN1 / AIN2 | GPIO5_C2 / C3 | 178 / 179 |
| BIN1 / BIN2 | GPIO5_C4 / C5 | 180 / 181 |
| E1A / E1B | GPIO5_C6 / C7 | 182 / 183 |
| E2A / E2B | GPIO5_D0 / D1 | 184 / 185 |
| GND | 开发板 GND | 必须共地 |
| Output_IO 5V | — | 给编码器供电（模块自身 5V 输出） |
| VM / GND2 | 12V 适配器 | 电机功率电源+共地 |

### 5.2 电机控制（方向 GPIO + PWM）

方向：`echo out > direction` 后写 value；PWM 走 `/sys/class/pwm/`：

```bash
ls /sys/class/pwm/                 # 找 pwmchipN
echo 0 > /sys/class/pwm/pwmchipN/export
echo 100000 > pwmchipN/pwm0/period      # 10kHz = 100000ns
echo  50000 > pwmchipN/pwm0/duty_cycle  # 50%
echo 1 > pwmchipN/pwm0/enable          # 使能输出
```

> 控制器/通道到 pwmchipN/pwmM 的对应关系以板上实测为准（`ls /sys/class/pwm/`）。

### 5.3 编码器读取（Linux 上无硬件正交解码）

方案 A（推荐，中等转速够用）：GPIO `edge=both` + `poll()`，仅统计 A 相边沿作为计数、读 B 相电平判方向（等价单相 2 倍频）：

```bash
echo 182 > /sys/class/gpio/export
echo in > /sys/class/gpio/gpio182/direction
echo both > /sys/class/gpio/gpio182/edge
# 之后用 poll() 等 POLLPRI，读 value 并 rewind
```

方案 B（低速/高精度）：内核模块用 GPIO IRQ + 4 倍频状态机计数（性能最好，开发量最大）。
方案 C（最简单）：10ms 定时线程轮询 A/B 电平做状态机解码（CPU 占用低但高速时易丢计数）。

### 5.4 控制循环（对应 STM32 的 10ms 中断）

用 `timerfd`/`clock_nanosleep` 建 10ms 周期线程：读两路编码器计数差 → 增量式 PI（Kp=1、Ki=3，限幅 ±100% 占空比）→ 写 PWM duty + 方向脚。

### 5.5 移植对照表

| STM32 侧 | RV1126B/Linux 侧 |
| --- | --- |
| TIM3 CH3/CH4 PWM 输出 | `/sys/class/pwm/pwmchipN/pwmM` duty_cycle |
| GPIO_SetBits/ResetBits 方向脚 | `/sys/class/gpio/gpioN/value` |
| TIM 编码器接口模式（硬件 4 倍频） | GPIO edge 中断计数（或状态机解码） |
| TIM1 10ms 中断 | 10ms 定时线程（timerfd / nanosleep） |
| 增量式 PI 速度环 | 同公式搬移，输出映射为 duty_cycle |
| ADC 电池电压检测 | 可选：SARADC（GPIO6_A0~A7 复用为 SARADC1_IN0~7） |

### 5.6 注意事项

1. **电平**：RV1126B GPIO 为 3.3V，D153B 的 VCC=5V 逻辑兼容 3.3V 输入，但**编码器电源按模块 5V 供电**（AB 输出高电平≈5V）——若直连 RV1126B GPIO 会超 3.3V！
   - 解决：编码器改用模块的 3V3 供电（3.3V），或经电平转换/分压后再进 GPIO
2. **共地**：开发板 GND、模块 GND1、外接电源 GND2 必须共地。
3. **电流**：MG310 堵转电流可能超过 TB6612 的 3.2A 峰值，避免长时间堵转；VM 勿超 13.5V。
4. **编码器方向**：A/B 相接反只会导致计数为负，软件取负号即可。
5. **快速验证**：转动电机时用万用表测 GND-AB 相约 1.6~1.8V 摆动即正常（无示波器排查法）。

## 六、待确认与下一步

1. 在板卡上执行 `ls /sys/class/gpio/ /sys/class/pwm/` 与 `cat /sys/kernel/debug/gpio`，确认 GPIO5_B/C/D 组是否可用、PWM3 对应哪个 pwmchip。
2. 确认底板排针上引出了哪几个 GPIO（需底板原理图），并确认未被 WiFi/BT/DSI 占用。
3. 确认 MG310 铭牌上的**减速比与编码器线数**，代入测速公式。
4. 确认编码器供电电压（用模块 3V3 还是 5V），必要时加电平转换，保护 3.3V GPIO。
5. 后续可写：`motor_ctl`（C++/Python）——封装 GPIO/PWM/编码器/10ms PI 环，并提供 `rtc_push_ctl.py` 那样的命令行控制。

## 七、参考文件索引

| 内容 | 路径 |
| --- | --- |
| 编码器例程（单路） | `D:\...\2.编码器的使用教程与测速原理\编码器例程\1.STM32F1例程(1)\STM32F103_Encoder_demo` |
| 双电机闭环例程 | `D:\...\4.例程源码\1.STM32F1例程\2.D153B（双路驱动带稳压版）例程\D153Bdemo（霍尔编码器）2025.7.7(1)` |
| TB6612 手册/线序图 | `D:\...\1.用户手册与使用视频教程\电机驱动模块使用手册—TB6612(2025.08.27).pdf`、`TB6612带稳压模块问题排查和检测方法(2025.07.10).pdf`（P4 线序图） |
| D153C 原理图 | `D:\...\5.原理图\2.TB6612双路驱动稳压模块原理图（D153C）.pdf` |
| RV1126B 引脚复用表 | `E:\...\04-硬件资料\04-管脚分配表\FET1126B-S引脚复用表（elf）.xlsx`（`对照表` 工作表 Alt0~Alt8 列） |
| GPIO 命令行测试 | `E:\...\01-教程文档\...\ELF-RV1126B开发板快速使用手册.pdf`（3.1.11 节，PDF 第 43~45 页） |

> 备注：编码器例程目录下的 `STM32例程对应接线说明.txt` 属于 D103A 单路电机接法（PWMA=B6/AIN1=B8/AIN2=B7），与同目录编码器例程使用的 PB6/PB7 冲突，以工程代码为准。





