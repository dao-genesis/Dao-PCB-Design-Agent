"""eprj2_codec — 嘉立创EDA Pro `.eprj2` 工程文件本源编解码器。

逆向定界（本会话三层序列化模型 + 字节级回写实证）：
  1) **加密 op-log（落盘日志态）**：`history_data.dataStr` 每行是一个文档的
     源记录流（`{"type":TAG}||{payload}|` 形式，与 `getDocumentSource` 同构），
     经 **gzip(level1) → AES-128-GCM → base64** 落盘。
       - key = 该分支 `project_history_<branch>.key`（16 字节，hex）
       - iv  = 该 history 行 `uuid` 的 hex 前缀（16 字节；`-N` 后缀非 hex 被截断，
               故同一文档多段共用 IV —— 这正解释了各段密文前缀相同）
       - 明文 = gzip 解压后的源记录流；密文 = AES-GCM(ct)||tag(16B)
  2) **materialized 明文态**：`documents.dataStr` / `coppers` / `texts` 等是
     另一套 `["TYPE",...]` 换行 JSON 数组格式（保存/分发态快照，便携可读）。
  3) **export 态**：`sys_FileManager.getDocumentSource` 是只读导出的 live 序列化。

本模块实现 op-log 层的 **解密/加密对称编解码**（加解密 round-trip 已实证无损），
既是 **READ 原语**（零 GUI 直读任意 `.eprj2` 全量 live 源记录流），也是
**WRITE 原语**——**headless 直写 PCB 文件已实证可行**（见下）。

★ **写权威面定界（本会话字节级实证·一波三折后的真结论）**：
  关键混淆变量是 **Service Worker CacheStorage** 里的**明文** `localSave`/`project`
  缓存（`https://client/localSave/<id>?key=..` → `{"type":"DOCHEAD"..PCB..}`）。
  编辑器 open 时**优先喂该热缓存**，故先前直接改 `.eprj2` 看似"不生效"（缓存仍是旧值），
  曾一度误判「`.eprj2` 非权威」。**清掉该缓存强制 cache-miss 后**：改
  `"Top Layer"→"DAOTOPXX"` 写回 `.eprj2` → 重开 `getDocumentSource` **出 DAOTOPXX**、
  且 **DRC=0 CLEAN**。∴ **cache-miss 时 `.eprj2` history_data(本模块的加密 op-log)
  即权威面**；`web.db`/IndexedDB/recovery/`snapshot` 实测均空,只此一处缓存作梗。
  写路径 = `edit_docs()` 改 op-log → `invalidate_doc_cache()` 清 SW 缓存 → 重开。
  **全新工程无缓存,首开即读 `.eprj2`,无须清。** typed RPC primitive 仍是另一条
  (live 会话内)写信道,二者并存:文件级直写(本模块) vs 会话级 RPC。

加密方案取自 app.js `class m4`（aes-128-gcm；encrypt(ivHex, plaintext) =
gzipSync(level1) 后 GCM，附 16B authTag；decrypt 取末 16B 为 tag）。
"""
import base64
import glob
import gzip
import os
import sqlite3

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

TAG_LEN = 16


def _hex_prefix(s):
    """取字符串的 hex 前缀（Node `Buffer.from(s,'hex')` 语义：遇非 hex 即止）。"""
    out = []
    for ch in s:
        if ch in "0123456789abcdefABCDEF":
            out.append(ch)
        else:
            break
    h = "".join(out)
    if len(h) % 2:
        h = h[:-1]
    return h


def key_map(con):
    """映射 {history_uuid: key}。

    每个 `project_history_<branch>` 表按 `uuid` 存多个文档/版本的 key；
    `history_data.history_uuid` 即指向该 uuid。各行需用**匹配的** key 解密。"""
    m = {}
    for (t,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'project_history_%'"):
        for uuid, key in con.execute(
                "SELECT uuid,key FROM '%s' WHERE key IS NOT NULL" % t):
            m[uuid] = key
    if not m:
        raise RuntimeError("no encryption key in project_history_* tables")
    return m


def branch_key(con):
    """兑容：返回任一 key（单分支单文档工程适用）。"""
    return next(iter(key_map(con).values()))


def decrypt_blob(key_hex, iv_source, b64data):
    """解密单条 op-log：key_hex/iv_source(hex 前缀)/base64 密文 → 明文源记录流。"""
    key = bytes.fromhex(key_hex)
    iv = bytes.fromhex(_hex_prefix(iv_source))
    blob = base64.b64decode(b64data)
    pt_gz = AESGCM(key).decrypt(iv, blob, None)  # blob = ct||tag(16)
    return gzip.decompress(pt_gz).decode("utf-8", "replace")


def encrypt_blob(key_hex, iv_source, plaintext):
    """加密单条 op-log（与 app.js 对称）：明文 → base64(GCM(gzip(pt))||tag)。

    注：Node gzipSync(level1) 与 Python 字节未必逐字节相同，但 GCM tag 覆盖的是
    本函数自产的密文、解密侧只需 gunzip 任意合法 gzip 流，故 LCEDA 可正常读回。
    """
    key = bytes.fromhex(key_hex)
    iv = bytes.fromhex(_hex_prefix(iv_source))
    gz = gzip.compress(plaintext.encode("utf-8"), compresslevel=1)
    blob = AESGCM(key).encrypt(iv, gz, None)  # 返回 ct||tag(16)
    return base64.b64encode(blob).decode("ascii")


def split_records(plaintext):
    """把源记录流拆成 [(tag, head_json, payload_json), ...]。

    形如 `{"type":TAG, ..}||{payload}|`（` |` 分隔记录、`||` 分隔头/载荷）。
    返回原样片段以便无损改写；只解析最外层。"""
    recs = []
    for chunk in plaintext.split("|\n") if "|\n" in plaintext else plaintext.split("| "):
        c = chunk.strip().rstrip("|").strip()
        if not c:
            continue
        recs.append(c)
    return recs


def iter_history(con):
    """遍历 history_data：返回 [(id, uuid, history_uuid, plaintext)]（已解密）。"""
    km = key_map(con)
    out = []
    for rid, uuid, huid, ds in con.execute(
            "SELECT id,uuid,history_uuid,dataStr FROM history_data ORDER BY id"):
        out.append((rid, uuid, huid, decrypt_blob(km[huid], uuid, ds)))
    return out


def write_history(con, row_id, uuid, history_uuid, plaintext):
    """把明文重新加密写回指定 history_data 行（用该行 history_uuid 对应的 key、iv=uuid）。"""
    key = key_map(con)[history_uuid]
    b64 = encrypt_blob(key, uuid, plaintext)
    con.execute("UPDATE history_data SET dataStr=? WHERE id=?", (b64, row_id))


def open_eprj2(path):
    return sqlite3.connect(path)


# ── 写路径(cache-miss 时 .eprj2 op-log 即权威面,本会话实证) ──────────────
#
# 热路径权威 = Service Worker CacheStorage 的明文 localSave/project 条目;只要它
# 在,编辑器 open 直接喂缓存(故磁盘改动看似"不生效")。清掉该缓存即强制 cache-miss,
# 编辑器回退到从 .eprj2 history_data(本模块可读写的加密 op-log)重建——实证:改
# `"Top Layer"→"DAOTOPXX"` 写回 .eprj2 + 清缓存 + 重开 → getDocumentSource 出
# DAOTOPXX 且 DRC=0 CLEAN。**全新工程本就无缓存,首开即读 .eprj2,无须清。**

def _lceda_profile_cache(profile_dir=None):
    if profile_dir:
        return profile_dir
    cands = sorted(glob.glob(os.path.expanduser("~/.config/LCEDA-Pro/cache.*")))
    if not cands:
        raise RuntimeError("找不到 LCEDA 配置缓存目录 ~/.config/LCEDA-Pro/cache.*")
    return cands[-1]


def invalidate_doc_cache(profile_dir=None):
    """清除 Service Worker CacheStorage,强制编辑器下次 open 从 .eprj2 重建。

    **须在编辑器进程已停止时调用**(文件锁 + 避免内存态回写覆盖)。
    清的是文档缓存层,非工程文件;编辑器会按 .eprj2 重新编译,无损。
    返回被清的路径(不存在则返回 None)。"""
    import shutil
    cs = os.path.join(_lceda_profile_cache(profile_dir), "Service Worker",
                      "CacheStorage")
    if os.path.isdir(cs):
        shutil.rmtree(cs)
        return cs
    return None


def edit_docs(path, transform):
    """对 .eprj2 每条 op-log 明文应用 transform(plaintext)->plaintext|None,
    有变更则重加密写回。返回被改写的 row id 列表。

    这是 headless 直写 PCB 文件的核心写原语:程控改记录流(改网名/层/几何/
    增删 primitive 记录),不经 GUI。改完须 invalidate_doc_cache() 再重开。"""
    con = open_eprj2(path)
    changed = []
    for rid, uuid, huid, plain in iter_history(con):
        new = transform(plain)
        if new is not None and new != plain:
            write_history(con, rid, uuid, huid, new)
            changed.append(rid)
    con.commit()
    con.close()
    return changed


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else sorted(
        glob.glob(os.path.expanduser(
            "~/Documents/LCEDA-Pro/projects/*.eprj2")))[-1]
    con = open_eprj2(p)
    print("file:", os.path.basename(p))
    for rid, uuid, huid, plain in iter_history(con):
        head = plain[:120].replace("\n", " ")
        # 第二条记录通常是 DOCHEAD，含 docType
        dt = ""
        if '"docType"' in plain:
            i = plain.find('"docType"')
            dt = plain[i:i + 40]
        print("  id=%-2d len=%-7d %s | %s" % (rid, len(plain), dt, head[:70]))
