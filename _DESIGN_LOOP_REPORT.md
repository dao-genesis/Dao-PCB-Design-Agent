# 实践报告 · 亲手布通一块 PCB (ams1117_power)

- 板: `ams1117_power` — AMS1117-3.3V稳压子模块 (通用电源块)
- 链路: inline → **netbind** → **route_maze** → KiCad 真 DRC
- 结果: **6/6 飞线布通**, 135 段走线, 总长 77.928mm

## 每阶段 KiCad 真 DRC (errors / unconnected)

| 阶段 | errors | warnings | unconnected | 备注 |
|------|-------|----------|-------------|------|
| inlined(初始) | 0 | 2 | 0 |  |
| netbind(绑网后) | 0 | 2 | 6 | 绑定9/未绑0 |
| route_maze(布线后) | 0 | 2 | 0 | 飞线6/6 135段 1.6s |

## 道理
> 占位生焊盘, 焊盘生连接, 连接生导通之板. 先成其通(0 unconnected),
> 再以真 DRC 涤其错(0 errors). 朴素直线布线会撞短路, 迷宫避障布线则
> 择空而行 —— 水善利万物而不争. 知止于真引擎判语, 不自欺.