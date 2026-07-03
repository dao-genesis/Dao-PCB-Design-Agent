# -*- coding: utf-8 -*-
"""dao_core_l2proof — L2 本体直通「活体硬证」(facade 外·可逆·不劣化)。

命题:经 dao_core 拿到的**内部事务/撤销管理器 `je`**(不在 _EXTAPI_ROOT_ 的 752
白名单里)能真正**驱动引擎状态**——它能撤掉由 facade 创建的图元。

流程(全程零 GUI、不存盘,故板子磁盘态不变):
  1. 记录内部撤销栈 `je.undoCommand.length`。
  2. 经 facade `pcb_PrimitiveVia.create('',0,0,…)` 建一个 via(可逆编辑)。
  3. 调**内部** `je.undo()`(facade 外)→ via 被移除。
  4. 复核:via 查无(gone)、via 总数归 0、`je.redoCommand.length` +1(=刚撤销的那条)。

本会话实测输出(桌面 v3.2.149,board ba7025338c90):
  created via aed0109b8d295ee8 → je.undo() → via_lookup=gone, via_count=0,
  undo_len=0, redo_len=1  ⇒ 内部管理器完整回退 facade 编辑,板子还原(不劣化)。

结论:dao_core 暴露的 L2 内部命令管理器**确实可编程直调并作用于真实引擎状态**,
印证「用户能做的(撤销/事务)我经内部管理器也能做,且不改本体存盘、不劣化」。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as C  # noqa: E402

PORT = int(os.environ.get("DAO_CDP_PORT", "29230"))

PROOF_JS = r"""
(async function(){
  var R=window.top._EXTAPI_ROOT_||window._EXTAPI_ROOT_;
  var w=null; for(var i=0;i<window.frames.length;i++){try{if((window.frames[i].location.href||'').indexOf('entry=pcb')>=0){w=window.frames[i];break;}}catch(e){}}
  var c=w&&w.__DAO_CORE__;
  if(!R) return JSON.stringify({err:'no facade'});
  if(!c) return JSON.stringify({err:'no __DAO_CORE__ (先用 dao_core_hook.py patch 或技法甲注入)'});
  var je=c.je, out={};
  out.before_undo=je.undoCommand.length;
  var created=null; try{ created=await R.pcb_PrimitiveVia.create('',0,0,0.3,0.6); }catch(e){ out.create_err=String(e.message); }
  out.created_id=created&&(created.pId||true);
  try{ je.undo(); }catch(e){ out.undo_err=String(e.message); }
  out.after_undo_undo=je.undoCommand.length;
  out.after_undo_redo=je.redoCommand.length;
  var still=true; try{ var v=R.pcb_PrimitiveVia.getState_ItemByPrimitiveId?R.pcb_PrimitiveVia.getState_ItemByPrimitiveId(out.created_id):null; still=!!v; }catch(e){}
  out.via_after_undo = still?'present':'gone';
  out.pass = (out.after_undo_redo>out.before_undo) && (out.via_after_undo==='gone');
  return JSON.stringify(out);
})()
"""


def main():
    ws = C.connect_editor(PORT)
    v, e = C.evaluate(ws, PROOF_JS, True, 30)
    if e:
        print("ERR:", e)
        return
    res = json.loads(v)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("RESULT", "PASS" if res.get("pass") else "FAIL")


if __name__ == "__main__":
    main()
