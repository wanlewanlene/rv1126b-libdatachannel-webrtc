# attic/ —— 历史草稿（不参与编译与运行）

本目录存放**未被任何构建脚本引用**的早期草稿，仅作参考保留，不参与编译：

| 文件 | 原位置 | 状态 |
| --- | --- | --- |
| `Video_capture_and_encoding.cpp` | 仓库根 | main.cpp 中 `V4L2Capture` + `MppEncoder` 的早期片段；引用外部未声明变量，独立编译不通过 |
| `WebRTC_Connection_Management.cpp` | 仓库根（原名含空格） | main.cpp 中 `WebRTCStreamer::createPeerConnection` 的早期草稿；依赖未声明的发包函数 |

依据：
- `build.sh` 只编译 `cpp/main.cpp`
- 全仓无 `#include` 引用这两个文件

如需删除，可直接删除本目录；不影响板端运行。
