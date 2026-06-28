# 实践报告 · 亲手布通一块 PCB (gd32f103_minimal)

- 板: `gd32f103_minimal` — GD32F103C8T6最小系统 — STM32F103引脚兼容国产替代，成本↓50%
- 链路: inline → **netbind** → **freerouting(本源生态自动布线)** → KiCad 真 DRC
- 结果: **243 段走线** (网数 37, Freerouting 自报未布 1, 9.97s)

## 每阶段 KiCad 真 DRC (errors / unconnected)

| 阶段 | errors | warnings | unconnected | 备注 |
|------|-------|----------|-------------|------|
| inlined(初始) | 27 | 39 | 0 | err:clearance,courtyards_overlap,solder_mask_bridge |
| spread(拉开后) | 0 | 6 | 0 |  |
| netbind(绑网后) | 0 | 6 | 37 | 绑定66/未绑6 |
| freerouting(生态自动布线) | 0 | 6 | 0 |  |

## 道理
> 占位生焊盘, 焊盘生连接, 连接生导通之板. 先成其通(0 unconnected),
> 再以真 DRC 涤其错(0 errors). 朴素直线布线会撞短路, 迷宫避障布线则
> 择空而行 —— 水善利万物而不争. 知止于真引擎判语, 不自欺.