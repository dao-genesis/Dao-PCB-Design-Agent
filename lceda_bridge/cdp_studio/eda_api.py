#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eda_api — 嘉立创EDA Pro Web 官方接口的高层 Python 绑定(覆盖全部 94 命名空间 / 701 方法)。

知其雄守其雌:用最小操作逻辑覆盖最大功能。属性即接口,直调即下达:

    from eda_api import EDA
    eda = EDA()
    eda.dmt_Project.getAllProjectsUuid()                 # → [...]
    eda.sys_ToastMessage.openNormal("hello from agent")  # 任意命名空间.方法
    eda.call("dmt_Project.getCurrentProjectInfo")        # 等价字符串寻址

特性:
  · 稳定:单连接线程安全(加锁串行化 CDP 请求);socket 异常自动重连重试。
  · 并发:连接池 map(),每 worker 独立 CDPSession,真正多并发直驱。
  · 自省:加载 eda_api_catalog.json 校验命名空间/方法(未知则 warn,不阻断)。

依赖:仅标准库 + dao_eda_cdp_driver(同目录)。
环境变量:DAO_CDP_PORT(默认 29229)
"""
import json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d

_CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eda_api_catalog.json")


def load_catalog(path=_CATALOG_PATH):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class EdaError(RuntimeError):
    pass


class EdaConn:
    """单条到编辑器页的 CDP 连接,线程安全 + 自动重连。"""

    def __init__(self, port=None):
        self.port = port or d.CDP_PORT
        self._ws = None
        self._lock = threading.Lock()

    def _connect(self):
        self._ws = d.connect_editor(self.port)

    def call(self, ns_api, args=None, timeout=30, retries=2):
        last = None
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    if self._ws is None:
                        self._connect()
                    res = d.call_eda(self._ws, ns_api, args or [], timeout=timeout)
                except Exception as ex:
                    self._ws = None  # 触发下次重连
                    last = {"ok": False, "err": "CONN " + str(ex)}
                    res = None
            if res is not None:
                if res.get("ok"):
                    return res.get("ret")
                err = str(res.get("err", ""))
                # 连接/上下文类错误重试;业务类错误直接抛
                if attempt < retries and ("CONN" in err or "NO_RESULT" in err or "Inspected target" in err):
                    self._ws = None; time.sleep(0.4); continue
                raise EdaError("%s -> %s" % (ns_api, err))
            if attempt < retries:
                time.sleep(0.4); continue
            raise EdaError("%s -> %s" % (ns_api, last and last.get("err")))


class _NS:
    """命名空间代理:eda.dmt_Project.method(...)。"""

    def __init__(self, eda, name):
        self._eda = eda
        self._name = name

    def __getattr__(self, method):
        if method.startswith("_"):
            raise AttributeError(method)
        ns, meth = self._name, method
        eda = self._eda
        eda._check(ns, meth)

        def _invoke(*args, **kw):
            return eda._conn.call("%s.%s" % (ns, meth), list(args),
                                  timeout=kw.get("timeout", 30))
        _invoke.__name__ = "%s.%s" % (ns, meth)
        return _invoke

    def __dir__(self):
        cat = self._eda._catalog
        if cat and self._name in cat.get("namespaces", {}):
            return [m["name"] for m in cat["namespaces"][self._name]["methods"]]
        return []


class EDA:
    """门面:属性即命名空间,直调即接口。"""

    def __init__(self, port=None, validate=True):
        self._conn = EdaConn(port)
        self._catalog = load_catalog() if validate else None
        self._warned = set()

    # --- 寻址 ---
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return _NS(self, name)

    def call(self, ns_api, *args, **kw):
        """字符串寻址直调: eda.call('dmt_Project.getCurrentProjectInfo')。"""
        if "." in ns_api:
            ns, meth = ns_api.split(".", 1)
            self._check(ns, meth)
        return self._conn.call(ns_api, list(args), timeout=kw.get("timeout", 30))

    def _check(self, ns, meth):
        cat = self._catalog
        if not cat:
            return
        nss = cat.get("namespaces", {})
        if ns not in nss:
            key = ("ns", ns)
            if key not in self._warned:
                self._warned.add(key)
                sys.stderr.write("[eda_api] WARN 未知命名空间: %s\n" % ns)
            return
        names = {m["name"] for m in nss[ns]["methods"]}
        if names and meth not in names:
            key = ("m", ns, meth)
            if key not in self._warned:
                self._warned.add(key)
                sys.stderr.write("[eda_api] WARN %s 无方法 %s\n" % (ns, meth))

    # --- 自省 ---
    def namespaces(self):
        cat = self._catalog
        return sorted(cat["namespaces"].keys()) if cat else []

    def methods(self, ns):
        cat = self._catalog
        if cat and ns in cat.get("namespaces", {}):
            return [m["name"] for m in cat["namespaces"][ns]["methods"]]
        return []

    def __dir__(self):
        return list(super().__dir__()) + self.namespaces()

    # --- 并发 ---
    def map(self, calls, workers=4):
        """并发执行多调用。calls: [(ns_api, [args]), ...] 或 ["ns.api", ...]。
        每 worker 独立 CDPSession,真正多并发。返回与输入同序的结果/异常列表。"""
        port = self._conn.port
        local = threading.local()

        def _one(item):
            ns_api, args = (item if isinstance(item, (tuple, list)) and len(item) == 2
                            and isinstance(item[1], (list, tuple)) else (item, []))
            conn = getattr(local, "conn", None)
            if conn is None:
                conn = EdaConn(port); local.conn = conn
            try:
                return conn.call(ns_api, list(args))
            except Exception as ex:
                return ex

        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(_one, calls))


if __name__ == "__main__":
    eda = EDA()
    print("namespaces=%d" % len(eda.namespaces()))
    # 冒烟:几个只读接口
    for api in ("dmt_Project.getAllProjectsUuid", "dmt_Project.getCurrentProjectInfo",
                "sys_Environment.getLanguage"):
        try:
            print("OK ", api, "->", json.dumps(eda.call(api), ensure_ascii=False)[:120])
        except Exception as e:
            print("ERR", api, "->", e)
