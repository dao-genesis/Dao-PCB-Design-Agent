/* ============================================================================
 * DAO 统一动词运行时 (前端) — 与 core/verbs.py 同一套 recipe、同一执行语义.
 * ----------------------------------------------------------------------------
 * 面板不再自己硬编码裸 eda_call: 它加载 verbs.manifest.js (由 core/verbs.py 生成),
 * 用下面的执行器把「高层动词」按 recipe 打到 EDA 引擎 —— 与后端 MCP/CLI/SDK
 * 说同一套动词、跑同一套「依次试候选、首个成功即返」逻辑. 根除前后端割裂.
 *
 * 依赖注入: edaCall(ns, method, args) -> Promise<value>  (app.js 提供).
 * 暴露: window.DaoVerbs = { resolveArgs, runTryPaths, execVerb, buildTools,
 *                          verbByToolName, toolName, manifest }.
 * ========================================================================== */
(function () {
  "use strict";

  var MANIFEST = window.DAO_VERBS_MANIFEST || { version: "0", verbs: [] };

  // arg 解析 — 与 verbs.resolve_args 严格一致 (递归解析嵌套对象/数组).
  function resolveOne(a, params) {
    if (a && typeof a === "object" && !Array.isArray(a)) {
      if ("$" in a) {
        var name = a["$"];
        return Object.prototype.hasOwnProperty.call(params, name) ? params[name] : (("def" in a) ? a.def : undefined);
      }
      var o = {};
      Object.keys(a).forEach(function (k) { o[k] = resolveOne(a[k], params); });
      return o;
    }
    if (Array.isArray(a)) return a.map(function (v) { return resolveOne(v, params); });
    return a;
  }
  function resolveArgs(argSpecs, params) {
    return (argSpecs || []).map(function (a) { return resolveOne(a, params); });
  }

  function splitPath(path) {
    var i = path.indexOf(".");
    return [path.slice(0, i), path.slice(i + 1)];
  }

  // 依次尝试候选 (path,args), 首个成功返回 {ok,path,result}; 全败 {ok:false,errors,tried}.
  // 与 verbs.run_try_paths 严格一致.
  async function runTryPaths(edaCall, candidates, params) {
    var errors = [], tried = [];
    for (var i = 0; i < candidates.length; i++) {
      var c = candidates[i], path = c.call;
      tried.push(path);
      try {
        var nm = splitPath(path);
        var res = await edaCall(nm[0], nm[1], resolveArgs(c.args || [], params));
        return { ok: true, path: path, result: res };
      } catch (e) {
        errors.push({ path: path, error: String((e && e.message) || e).slice(0, 300) });
      }
    }
    return { ok: false, errors: errors, tried: tried };
  }

  // 执行一个动词 (仅前端可执行的 kind: try_paths / fields / raw_call).
  async function execVerb(edaCall, verb, params) {
    params = params || {};
    var rq = (verb.input_schema && verb.input_schema.required) || [];
    for (var i = 0; i < rq.length; i++) {
      if (!Object.prototype.hasOwnProperty.call(params, rq[i])) {
        throw new Error("缺少必填参数: " + rq[i]);
      }
    }
    var r = verb.recipe, kind = r.kind;
    if (kind === "try_paths") return await runTryPaths(edaCall, r.candidates, params);
    if (kind === "fields") {
      var out = {};
      var keys = Object.keys(r.fields);
      for (var k = 0; k < keys.length; k++) {
        out[keys[k]] = await runTryPaths(edaCall, r.fields[keys[k]], params);
      }
      return out;
    }
    if (kind === "raw_call") {
      var nm = splitPath(params.path);
      return await edaCall(nm[0], nm[1], params.args || []);
    }
    throw new Error("该动词只能在后端执行 (kind=" + kind + ")");
  }

  // OpenAI tool 名不允许 '.', 用 '_' 代替 (与后端 Tool.to_openai 一致).
  function toolName(verbName) { return verbName.replace(/\./g, "_"); }

  function verbByToolName(name) {
    for (var i = 0; i < MANIFEST.verbs.length; i++) {
      var v = MANIFEST.verbs[i];
      if (v.name === name || toolName(v.name) === name) return v;
    }
    return null;
  }

  // 由 manifest 生成 OpenAI function-calling 工具 (仅前端可执行的动词).
  function buildTools() {
    return MANIFEST.verbs.filter(function (v) { return !v.backend_only; }).map(function (v) {
      return { type: "function", function: {
        name: toolName(v.name),
        description: v.description,
        parameters: v.input_schema,
      } };
    });
  }

  window.DaoVerbs = {
    manifest: MANIFEST,
    resolveArgs: resolveArgs,
    runTryPaths: runTryPaths,
    execVerb: execVerb,
    buildTools: buildTools,
    verbByToolName: verbByToolName,
    toolName: toolName,
  };
})();
