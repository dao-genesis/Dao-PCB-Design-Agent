# 嘉立创EDA专业版 · 桌面客户端本源接入(纯底层 · 零 GUI)

> 重新锚定本源:系统不为网页、不为屏幕点击而造,而是直接锚在**桌面软件本体**(Electron 主进程 +
> 离线核心)上。通过 Chrome 远程调试(CDP)在渲染层调用官方扩展接口 `window._EXTAPI_ROOT_`,
> 用 EDA 自身机制完成 新建工程 → 放置 → 布线 → 覆铜 → DRC → 导出,**全程零 GUI 点击**。

## 1. 客户端形态(逆向所得)

- 发行物:`lceda-pro-linux-x64-<ver>.zip`(本仓库实测 3.2.149)。镜像:
  `https://image.lceda.cn/files/lceda-pro-linux-x64-3.2.149.zip`
- 技术栈:Electron 36.3.1 / Chromium 136 / Node 22.15.1。
- 运行模式:`HALF_OFFLINE`(`config.json` 的 `type`)。模块(pro-api / pro-pcb / pro-sch /
  pro-panel / pro-mgr …)按需从 `https://modules.lceda.cn/` 拉取,核心在本地 `resources/app`。
- 数据目录 `Ke`:`~/Documents/LCEDA-Pro/`(projects / libraries / database / logs / config.json)。
- 内置本地服务(Koa 风格)路由:`/client/activationInfo`、`/client/activation`(POST →
  `replaceActivationFile`)、`/client/projectHistory`、`/client/libraryPaths` 等;另有
  `app://api/client/*` 自定义协议。

## 2. 许可 / 激活机制(逆向所得,合规复用账号免费许可)

启动校验 `Fa()` → `nl()`(见 `app.js`):

```
file = ~/Documents/LCEDA-Pro/lceda-pro-activation.txt          # JSON
license = obj["license"]            # "<spec_b64>,<sig_b64>"
fields  = base64decode(spec_b64).split("|")                    # 参与签名的字段名表
signed  = "".join(obj[name] for name in fields) + spec_b64
verify(RSA-SHA256, signed, sig_b64, 内置公钥 uy)                # 仅验签,不比对本机硬件
```

要点:`nl()` **只校验签名是否覆盖文件自身字段,不读取/比对当前机器硬件指纹**。因此用户在
`https://lceda.cn/page/desktop-client-activation`(登录态)经 `GET /api/downloadActivationFile`
取得的**账号免费激活文件**,放到任意机器的 `lceda-pro-activation.txt` 即可解锁(这是用户自己账号的
免费许可,合规)。

## 3. 一键启动(无头 · 远程调试)

```bash
bash lceda_bridge/desktop/launch_desktop.sh
# 环境变量:LCEDA_HOME(解压根目录)/ LCEDA_PORT(默认 29230)/ LCEDA_DISPLAY(默认 :99)
# 就绪后:curl http://127.0.0.1:29230/json  可见 page 目标 https://client/editor?...
```

启动器自动:探测客户端 → 起 Xvfb 虚拟显示 → `lceda-pro --no-sandbox
--remote-debugging-port=29230 --remote-allow-origins=*` → 等 CDP 就绪。

## 4. 装入激活文件并解锁(一次性引导)

```bash
# 文件:
python3 lceda_bridge/desktop/activate.py /path/to/lceda-pro-activation.txt
# 或直接粘贴全文 / 从 stdin:
cat lceda-pro-activation.txt | python3 lceda_bridge/desktop/activate.py -
```

`activate.py` 会:本地用内置公钥**预验签**(`cryptography` 可用时严格校验)→ 写入数据目录 →
经 CDP 重载渲染层 → 探测 `window._EXTAPI_ROOT_` 是否挂载,确认编辑器解锁。

## 5. 纯 RPC 驱动(零 GUI)

解锁后复用 `lceda_bridge/cdp_studio` 的官方接口客户端,**只需把端口指向桌面客户端**:

```bash
export DAO_CDP_PORT=29230
python3 - <<'PY'
import sys; sys.path.insert(0, "lceda_bridge/cdp_studio")
from eda_api import EDA
eda = EDA()                                   # 经 _EXTAPI_ROOT_ 直调官方接口
print(eda.dmt_Project.getCurrentProjectInfo())
PY
```

`cdp_studio` 已验证可用的能力(新建工程/原理图、社区取件、连线命名、同步 PCB、过孔布线、
GND 覆铜、DRC、Gerber/BOM/PnP 导出)在桌面端按同一 `_EXTAPI_ROOT_` 机制运行,无需任何屏幕点击。

> 网页版(pro.lceda.cn)相关的浏览器登录/点击自动化已**废弃**;PCB 构建一律走桌面本体 + RPC。
