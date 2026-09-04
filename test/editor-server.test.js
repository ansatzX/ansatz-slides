import assert from "node:assert/strict";
import { once } from "node:events";
import test from "node:test";
import { createEditorServer } from "../lib/editor-server.js";

async function withServer(callback) {
  const server = createEditorServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();

  try {
    await callback(`http://127.0.0.1:${address.port}`);
  } finally {
    server.close();
    await once(server, "close");
  }
}

test("serves the PPTD editor and its JavaScript modules", async () => {
  await withServer(async (url) => {
    const index = await fetch(`${url}/`);
    assert.equal(index.status, 200);
    assert.match(index.headers.get("content-type"), /^text\/html/);
    const html = await index.text();
    assert.match(html, /打开 PPTD 文件夹/);
    assert.match(html, /local-bridge\.js/);

    const bridge = await fetch(`${url}/local-bridge.js`);
    assert.equal(bridge.status, 200);
    assert.match(bridge.headers.get("content-type"), /^text\/javascript/);

    const wasm = await fetch(`${url}/neo-ppt/assets/pptd_wasm_bg-DPPWdROu.wasm`);
    assert.equal(wasm.status, 200);
  });
});

test("returns 404 for files outside the packaged editor", async () => {
  await withServer(async (url) => {
    const response = await fetch(`${url}/missing.js`);
    assert.equal(response.status, 404);
  });
});

test("supports HEAD requests without a response body", async () => {
  await withServer(async (url) => {
    const response = await fetch(`${url}/local-shell.css`, { method: "HEAD" });
    assert.equal(response.status, 200);
    assert.equal(await response.text(), "");
  });
});
