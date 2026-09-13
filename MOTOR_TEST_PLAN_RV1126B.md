# RV1126B 电机驱动：板级排查结果与测试方案

采集时间：2026-09-12 22:36（板卡 192.168.137.184，SSH 自动探测）

## 1. 板级排查结果（实测）

### 1.1 GPIO

| 项目 | 结果 |
| --- | --- |
| gpiochip4（GPIO4, 128~159） | 全部空闲 |
| gpiochip5（GPIO5, 160~191） | **全部空闲**（无任何内核占用） |
| gpiochip6（GPIO6, 192~223） | 全部空闲 |
| gpiochip7（GPIO7, 224~255） | gpio-226(pa-ctl)、gpio-231(reset) 已占用 |
| 实测 | `export 176` → direction=out、value=1 成功；`export 182` → edge=both 成功（需 root） |
| 中断能力 | `rockchip_gpio_irq` 正在服务触摸屏(rk801/edt-ft5406)，**GPIO 中断可用** |
| sysfs 权限 | `/sys/class/gpio/export` 仅 root 可写（`echo elf | sudo -S`） |

### 1.2 PWM（关键限制）

`/sys/kernel/debug/pwm` 实测：**3 个已使能通道全部被内核占用**

| pwmchip | 地址 | 占用者 | 映射 |
| --- | --- | --- | --- |
| pwmchip0 | 20e00000 | vdd-cpu（CPU 稳压器，polarity=inverse） | PWM0_CH0 |
| pwmchip1 | 20e20000 | backlight-dsi（DSI 背光，正在用） | PWM0_CH2 |
| pwmchip2 | 20f40000 | backlight-lcd（未启用） | PWM2_CH4 |

- 其余 25 个 PWM 节点在设备树中均为 `disabled`；`/sys/kernel/config` 无 device-tree 目录 → **不支持 DT overlay**，不能热加载
- PWM3 复用组名已确认：`pwm3m1-ch0-pins` = bank5 pin0 func7 → **GPIO5_C0（176）**，ch1→C1(177)、ch2→C2(178)、ch3→C3(179)，与引脚复用表一致
- 结论：**当前系统无法直接获得 2 路硬件 PWM**，需按下节方案之一解决

### 1.3 其他资源与运行状态

| 项目 | 结果 |
| --- | --- |
| I2C | `/dev/i2c-0`、`/dev/i2c-3`、`/dev/i2c-4` |
| SPI | `/dev/spidev1.0`、`/dev/spidev1.1` |
| Python | 板上 `/usr/bin/python3` 可用（便于写测试脚本） |
| 视频栈 | rtc-signal(3000/8080)、rv1126b_webrtc_push、reverse_player 均在运行 |
| CPU | 4 核在线，governor=ondemand，当前 71% idle；webrtc 与 reverse_player 都在 CPU2 |
| 内存 | 3941MB，空闲 3461MB |
| 温度/DMC | 44.6℃，DMC=performance/1332MHz（已锁频） |
| 磁盘 | rootfs 77%，/userdata 3% |

## 2. PWM 解决方案（三选一）

| 方案 | 做法 | 优点 | 缺点 |
| --- | --- | --- | --- |
| A 改设备树（最终方案） | SDK 中把 `&pwm3` 置 `okay` + `pinctrl-0 = <&pwm3m1_ch0_pins &pwm3m1_ch1_pins>`，重编内核/DTB 并烧写 | 8 路硬件 PWM，10kHz 零抖动 | 需编译+烧写，周期约半天 |
| B PCA9685 模块（最快落地） | I2C 接 i2c-3/4，模块 16 路 PWM 输出接 TB6612 PWMA/PWMB | 不改内核，即插即用 | 最高 1.6kHz，有轻微啸叫；需装 python3-smbus |
| C 软件 PWM | GPIO 位翻转 + 高优先级线程 | 不改任何东西 | 1kHz 级，抖动大，仅适合调试 |

建议：**先用 B 或 C 打通全链路（GPIO/编码器/闭环逻辑），最终切到 A**。

## 3. 需要测试的内容（清单）

### T1 引脚物理可达性（跳线环回，10 分钟）

用一根杜邦线把 **176（GPIO5_C0）↔ 182（GPIO5_C6）** 短接：
1. 176 设 out，输出 1/0 交替
2. 182 设 in，读 value → 应跟随变化
3. 182 设 edge=both，poll 等待中断 → 应收到与跳变次数相同的 POLLPRI

通过即证明：引脚 176/182 均 mux 到 GPIO、驱动能力与输入/中断链路正常。
依次对 177→183、178→184、179→185 重复（验证全部 8 个目标引脚）。

### T2 PWM 输出（示波器/万用表）

- 设 10kHz、50% → 万用表测平均电压≈1.65V（3.3V 档）；示波器看波形与频率
- 占空比 0/25/50/75/100% 五点校验线性

### T3 编码器链路

- 手转电机：计数应正负交替、无跳变突变；换算转速与手转速度吻合
- 方向一致性：正转计数增、反转减（与电机线极性定义一致）
- 最高频率测试：用信号发生器/手动快速转动，确认不丢计数（10ms 内计数与预期一致）

### T4 电机开环

- 正转/反转/停止/刹车四种状态与真值表一致
- 最小启动占空比（死区）测定：从 0 起逐步加，记录能稳定转动的最小值（通常 15~25%）
- 轮速-占空比曲线：20/40/60/80/100% 各测 3 次转速

### T5 速度闭环

- 目标 30/60/120rpm：稳态误差 ≤5%，超调 ≤10%
- 阶跃响应：0→100rpm 上升时间 ≤0.5s，无持续振荡
- 抗扰：手轻按负载，转速能恢复

### T6 位置闭环

- 目标 90°/360°/720°：重复 10 次，误差 ≤±2°，无累积漂移
- 到位后无来回抖动（死区设置合理）

### T7 保护

- 堵转 1s → 告警并停机
- 编码器断线（拔掉 AB 相）→ 计数不动 → 触发告警
- 12V 掉电/恢复 → 电机停止、程序不崩

### T8 与视频功能兼容（重点）

背景：现有 WebRTC 推流对延迟敏感（曾因 rkvdec2 停摆/DMC 降频导致卡顿），电机控制引入的中断与线程会争抢 CPU。

测试方法（对拍）：
1. 基线：只跑视频（正向推流 + 反向播放），记录 10 分钟内的 FPS、延迟、解码帧计数（用 `rtc_push_ctl.py` 的帧计数验证）
2. 叠加：启动电机控制（10ms 线程 + 编码器中断，电机以 50% 占空比空转）
3. 对比指标：视频 FPS 波动、端到端延迟增量、`dmesg` 是否有 rkvdec2 timeout、CPU 各核占用
4. 边界：电机急停/急启（最大电流冲击）瞬间观察视频是否丢帧
5. 长稳：连续运行 30 分钟，记录内存、温度、丢帧计数

通过标准：
- 视频 FPS 下降 <5%，无新增卡顿/解码器停摆
- 电机控制周期抖动 <1ms，控制不失效
- 系统温度 <75℃，无 OOM

## 4. 自动化排查方式

### 4.1 已有工具

| 脚本 | 用途 |
| --- | --- |
| `rtc_push_ctl.py` | 视频推流运维（板卡 IP 自动探测、重启、帧计数验证） |
| `_motor_probe.py` | 板级资源采集（GPIO/PWM/pinctrl/负载），本次排查使用 |

### 4.2 待落地：`motor_selftest.py`（板上运行）

一条命令自动完成：

```bash
sudo python3 motor_selftest.py --loopback      # T1 跳线环回自检
sudo python3 motor_selftest.py --encoder       # T3 编码器计数（可选 --motor 驱动）
sudo python3 motor_selftest.py --pwm           # T2 PWM（PCA9685 或 DTB 后）
sudo python3 motor_selftest.py --video-baseline --minutes 10   # T8 基线
sudo python3 motor_selftest.py --video-with-motor --minutes 10 # T8 叠加对比
```

输出：JSON + 人类可读报告（`/userdata/rtc/motor_test_YYYYmmdd_HHMM.json`），异常自动标红。

### 4.3 建议的自动化流程

1. 每次上电：跑 `--loopback`（3 秒，确认引脚链路没被固件改动破坏）
2. 改代码后：跑 `--encoder --motor-steps`（自动记录死区与转速曲线）
3. 每次发版前：跑 `--video-baseline` + `--video-with-motor` 对拍，生成对比报告

## 5. 与视频功能兼容的稳定性措施

### 5.1 CPU 与调度隔离

| 措施 | 说明 |
| --- | --- |
| 绑核 | 电机控制线程与编码器中断线程绑到 **CPU1/CPU3**（视频进程当前在 CPU2、node 在 CPU0） |
| 优先级 | 控制线程用 `SCHED_FIFO` 10~20（不要高于视频采集/编码线程） |
| 中断亲和 | `echo 1 > /proc/irq/<gpio_irq>/smp_affinity` 把 GPIO 中断分散到空闲核 |
| 周期 | 控制周期 10ms；编码器中断处理只做"读值+累加"，重活丢给周期线程 |

### 5.2 资源与电源

- 内存充足（空闲 3.4G），但避免大缓冲；控制进程常驻 <20MB
- **12V 独立供电 + 共地**，电机电流不经过开发板；USB 摄像头供电与电机分开，防止压降导致 UVC 掉线
- PWM 若用 PCA9685：走 i2c-3/4（避开被占用的总线），并确认无其他设备冲突

### 5.3 与既有故障模式的关系

- 已知 DMC 已锁 performance（防 rkvdec2 超时）；电机引入的额外内存带宽压力需在 T8 中复测
- 已知 RTW WiFi 驱动刷屏日志：电机测试日志请写到 /userdata，避免 rootfs 再次被写满（rootfs 现 77%）

### 5.4 上线方式

- 与视频系统一致：做成 systemd 服务 `motor-ctl.service`（Restart=always、开机自启、日志进 journald 且限流）
- 提供 `motor_ctl` 命令行（socket 常驻），并在退出/崩溃时自动 PWM=0、STBY=0
- 与 `run.sh` 的 DMC 锁频等既有步骤合并，不重复引入

## 6. 结论与行动顺序

**已确认可用（可立即开工）**：GPIO5 全组空闲、导出/输出/中断可用、I2C/SPI 可用、视频栈运行正常且余量充足。

**唯一硬阻塞**：2 路硬件 PWM —— 当前 3 路全被占用、其余未在设备树使能、无 overlay 支持。

建议顺序：

1. **今天**：接线做 T1 跳线环回（验证 176~185 八个引脚）→ 结论直接决定方案可行性
2. **随后**：用 PCA9685（方案 B）或软件 PWM 打通 T2~T7，把控制逻辑与编码器闭环调好
3. **并行**：在 SDK 中准备 pwm3 的设备树补丁（方案 A），编译并烧写，替换方案 B
4. **最后**：跑 T8 对拍（视频 + 电机）与 30 分钟长稳，之后转 systemd 上线

**待用户提供**：底板排针丝印图/原理图（确认 176~185 是否引出到排针）、MG310 铭牌减速比与线数、D153B 实物接线照片。