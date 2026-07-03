// Extension-host integration test (runs inside real VS Code):
//   xvfb-run -a code --no-sandbox --user-data-dir /tmp/ud \
//     --extensionDevelopmentPath=$REPO/vscode-dao-kicad \
//     --extensionTestsPath=$REPO/vscode-dao-kicad/test/integration.js \
//     --disable-workspace-trust $REPO
// Activates the extension, opens the home webview, waits for the bridge,
// then drives the same REST flow the single-page UI uses:
// tree -> render -> netlist -> build(job) -> drc.
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");

const OUT = process.env.DAO_TEST_LOG || path.join(os.tmpdir(), "dao_it.log");
const log = (m) => fs.appendFileSync(OUT, m + "\n");

function req(method, port, p, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const r = http.request({ host: "127.0.0.1", port, path: p, method,
      headers: data ? { "Content-Type": "application/json" } : {} }, (res) => {
      let b = "";
      res.on("data", (d) => (b += d));
      res.on("end", () => resolve({ code: res.statusCode, body: b }));
    });
    r.on("error", reject);
    if (data) r.write(data);
    r.end();
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

exports.run = async function () {
  const vscode = require("vscode");
  const ext = vscode.extensions.getExtension("dao.dao-kicad");
  if (!ext) throw new Error("extension dao.dao-kicad not found");
  await ext.activate();
  log("EXT_ACTIVATED");
  await vscode.commands.executeCommand("daoKicad.openHome");
  log("HOME_OPENED");

  const port = vscode.workspace.getConfiguration("daoKicad").get("port") || 9931;
  let h = null;
  for (let i = 0; i < 40 && !h; i++) {
    h = await req("GET", port, "/api/health").catch(() => null);
    if (h && h.code !== 200) h = null;
    await sleep(500);
  }
  if (!h) throw new Error("bridge did not come up");
  log("BRIDGE_OK " + h.body);

  const demo = "/usr/share/kicad/demos/ecc83";
  if (!fs.existsSync(demo)) { log("DEMO_SKIP"); return; }

  const tree = JSON.parse((await req("GET", port,
    "/api/tree?root=" + encodeURIComponent(demo))).body);
  if (!tree.ok || !tree.projects.length) throw new Error("tree failed");
  log("TREE_OK " + tree.projects.length);

  const sch = tree.projects[0].sch[0];
  const svg = await req("GET", port,
    "/api/render/sch?path=" + encodeURIComponent(sch));
  if (svg.code !== 200 || !svg.body.includes("<svg")) throw new Error("render failed");
  log("RENDER_OK " + svg.body.length);

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "daoit-"));
  log("TMP " + tmp + " SCH " + sch);
  const netRes = await req("POST", port, "/api/netlist",
    { sch, out: path.join(tmp, "b.net") });
  log("NETLIST_RAW " + netRes.code + " " + netRes.body);
  const net = JSON.parse(netRes.body);
  if (!net.ok) throw new Error("netlist failed: " + netRes.body);
  log("NETLIST_OK");

  const pcb = path.join(tmp, "b.kicad_pcb");
  const job = JSON.parse((await req("POST", port, "/api/build",
    { netlist: net.net, out: pcb, project_dir: demo })).body);
  if (!job.job) throw new Error("build job not created");
  let st = null;
  for (let i = 0; i < 240; i++) {
    st = JSON.parse((await req("GET", port, "/api/job?id=" + job.job)).body);
    if (st.done) break;
    await sleep(2000);
  }
  if (!st || !st.done || !st.result.ok) throw new Error("build failed: " + JSON.stringify(st));
  log("BUILD_OK fp=" + st.result.footprints);

  const drc = JSON.parse((await req("POST", port, "/api/drc", { pcb })).body);
  if (typeof drc.violations !== "number") throw new Error("drc failed");
  log("DRC_OK violations=" + drc.violations + " unconnected=" + drc.unconnected);

  await vscode.commands.executeCommand("daoKicad.restartBridge");
  for (let i = 0; i < 40; i++) {
    const r = await req("GET", port, "/api/health").catch(() => null);
    if (r && r.code === 200) { log("RESTART_OK"); return; }
    await sleep(500);
  }
  throw new Error("bridge did not come back after restart");
};
