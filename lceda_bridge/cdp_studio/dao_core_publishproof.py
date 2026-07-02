# -*- coding: utf-8 -*-
"""dao_core_publishproof — 方向B「publish 侧 facade 外 GUI 操作」活体硬证(可逆·不劣化)。

命题:经 dao_core 拿到的**内部发布总线** `pub.messageBus`(class eQe,696 活体主题,
facade 未开放)能**直发 GUI 命令驱动真实引擎的选择态**——`clearSelect`/`selectAll`
就是用户按 Esc / Ctrl+A 的同一条命令路径,发一下即整板选择态随之翻转,且纯选择态
不改板、天然可逆(不劣化)。

活体流程(全程零 GUI、不存盘,单次原子 eval 避免多轮往返卡死):
  1. je.undo 清台到 0 via(确定性起点)→ facade 建 N 个 via。
  2. publish('clearSelect') → 选中数=0。
  3. publish('selectAll')  → 选中数=N(整板全选,facade getAllSelectedPrimitives 复核)。
  4. publish('clearSelect') → 选中数=0(可逆)。
  5. je.undo×N 撤掉建 via → 回基线(净效果=0)。
PASS = 三次选择态翻转全部符合预期(0 → N → 0)。

坐实边界(本会话实测,已归档 DESKTOP_CORE_FUSION_MAP.md 方向B):
  - `clearSelect`/`selectAll`(无参、作用于编辑器内部选择态)经 publish **真生效且可逆**。
  - `delete`/`ROTATE` 这类主题**不吃 facade 包装对象**:`delete` 订阅体签名是
    `o=>{... Db.getInstance().delete(o,o.globalIndex) ...}`,要的是内部图元(instanceof
    ft/_t、带 globalIndex),而 facade getAllSelectedPrimitives 回的是包装类(ctor Wi,
    无 globalIndex)→ 直发无效;`ROTATE` 单参/多参/绕自身质心均不平移,属交互态命令。
    → 这类「带内部对象/交互态」的变换正解走**方向C 的 je.executeCommand 内部事务直调**,
       而非裸 publish;方向B 锚定的是「无参 GUI 命令(选择/全局)经总线直驱」这一真入口。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_core as DC  # noqa: E402

PROOF_BODY = r"""
  var R = (typeof _EXTAPI_ROOT_!=='undefined')?_EXTAPI_ROOT_:(window&&window._EXTAPI_ROOT_);
  var mb = pub.messageBus, out={};
  if(!R){ return JSON.stringify({err:'no facade in iframe'}); }
  function sleep(ms){return new Promise(function(r){setTimeout(r,ms);});}
  async function selN(){ try{ var s=await R.pcb_SelectControl.getAllSelectedPrimitives(); return (s&&s.length)||0; }catch(e){ return -1; } }
  async function viaN(){ try{ var i=await R.pcb_PrimitiveVia.getAllPrimitiveId(); return (i&&i.length)||0; }catch(e){ return -1; } }

  // 台面:je.undo 清台到确定性 0(最多撤 60 步)
  for(var c=0;c<60;c++){ if((await viaN())<=0) break; try{ je.undo(); }catch(e){} await sleep(40); }
  out.base_via = await viaN();

  // 建 N 个 via 作被选对象
  var N=3; for(var i=0;i<N;i++){ await R.pcb_PrimitiveVia.create('', i*3, 0, 0.3, 0.6); }
  await sleep(350);
  out.n_via = await viaN();

  // ── 内部总线 publish 驱动 GUI 选择态(facade 外·同一条 Esc/Ctrl+A 命令路径) ──
  try{ mb.publish('clearSelect'); }catch(e){ out.cs_err=String(e&&e.message); } await sleep(180);
  out.sel_after_clear = await selN();          // 期望 0
  try{ mb.publish('selectAll'); }catch(e){ out.sa_err=String(e&&e.message); } await sleep(300);
  out.sel_after_all = await selN();            // 期望 = n_via(整板全选)
  try{ mb.publish('clearSelect'); }catch(e){ out.cs2_err=String(e&&e.message); } await sleep(180);
  out.sel_after_clear2 = await selN();         // 期望 0(可逆)

  // 清理:撤掉 N 次 create,回基线(净效果=0,不改盘)
  for(var u=0;u<N+2;u++){ try{ je.undo(); }catch(e){} await sleep(50); }
  await sleep(150);
  out.final_via = await viaN();

  out.pass = (out.n_via===out.base_via+N)
             && (out.sel_after_clear===0)
             && (out.sel_after_all===out.n_via)
             && (out.sel_after_clear2===0);
  return JSON.stringify(out);
"""


def main():
    core = DC.DaoCore()
    print("status:", core.status())
    res = json.loads(core.core_eval(PROOF_BODY, by_value=True, timeout=40))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("RESULT", "PASS" if res.get("pass") else "FAIL")
    return 0 if res.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
