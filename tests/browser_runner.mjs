/** Execute synthetic MCP host assertions with real browser time. */
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
const [executable, url, profile] = process.argv.slice(2);
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let stderr = "";
const browser = spawn(
  executable,
  [
    "--headless",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--remote-debugging-port=0",
    "--user-data-dir=" + profile,
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "pipe"] },
);
browser.stderr.on("data", (chunk) => {
  stderr = (stderr + chunk).slice(-1000);
});
const exited = new Promise((resolve) => browser.once("exit", resolve));
let socket;
try {
  let port;
  const startupDeadline = Date.now() + 20000;
  while (!port && Date.now() < startupDeadline) {
    try {
      port = (
        await readFile(path.join(profile, "DevToolsActivePort"), "utf8")
      ).split("\n")[0];
    } catch {}
    if (!port) {
      if (browser.exitCode !== null)
        throw Error("Browser exited during startup: " + stderr);
      await pause(100);
    }
  }
  if (!port) throw Error("Browser did not start: " + stderr);
  const targets = await (
    await fetch(`http://127.0.0.1:${port}/json/list`)
  ).json();
  socket = new WebSocket(
    targets.find((target) => target.type === "page").webSocketDebuggerUrl,
  );
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  const pending = new Map();
  let sequence = 0;
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    message.error
      ? request.reject(Error(message.error.message))
      : request.resolve(message.result);
  });
  socket.addEventListener("close", () => {
    for (const request of pending.values())
      request.reject(Error("Browser connection closed"));
    pending.clear();
  });
  const call = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = ++sequence;
      pending.set(id, { resolve, reject });
      socket.send(JSON.stringify({ id, method, params }));
    });
  const evaluate = async (expression) => {
    const result = await call("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (result.exceptionDetails)
      throw Error(
        result.exceptionDetails.exception?.description ||
          result.exceptionDetails.text,
      );
    return result.result?.value;
  };
  const click = async (position) => {
    for (const type of ["mousePressed", "mouseReleased"])
      await call("Input.dispatchMouseEvent", {
        type,
        ...position,
        button: "left",
        clickCount: 1,
      });
  };
  const settle = () =>
    evaluate(
      "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))",
    );
  const auditPointer = async () => {
    for (const width of [320, 640]) {
      await click(await evaluate(`window.preparePointer(${width})`));
      await settle();
      await evaluate("window.assertPointer(true)");
      await click(await evaluate("window.pointerPosition()"));
      await settle();
      await evaluate("window.assertPointer(false)");
      await call("Input.dispatchKeyEvent", {
        type: "rawKeyDown",
        key: "Enter",
        code: "Enter",
        windowsVirtualKeyCode: 13,
      });
      await call("Input.dispatchKeyEvent", {
        type: "char",
        text: "\r",
        key: "Enter",
        code: "Enter",
        windowsVirtualKeyCode: 13,
      });
      await call("Input.dispatchKeyEvent", {
        type: "keyUp",
        key: "Enter",
        code: "Enter",
        windowsVirtualKeyCode: 13,
      });
      await settle();
      await evaluate("window.assertPointer(true)");
    }
    await evaluate(
      "document.getElementById('outcome').textContent='BROWSER_ACCEPTANCE_OK'",
    );
  };
  await call("Page.enable");
  await call("Runtime.enable");
  await call("Emulation.setDeviceMetricsOverride", {
    width: 1200,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await call("Page.navigate", { url });
  const deadline = Date.now() + 30000;
  let outcome;
  while (Date.now() < deadline) {
    const evaluated = await call("Runtime.evaluate", {
      expression: "document.getElementById('outcome')?.textContent",
      returnByValue: true,
    });
    outcome = evaluated.result?.value;
    if (outcome === "POINTER_READY") {
      await auditPointer();
      outcome = "BROWSER_ACCEPTANCE_OK";
    }
    if (outcome === "BROWSER_ACCEPTANCE_OK") break;
    if (outcome?.startsWith("FAILED:")) throw Error(outcome);
    await pause(50);
  }
  if (outcome !== "BROWSER_ACCEPTANCE_OK")
    throw Error("Browser assertions did not finish: " + outcome);
  process.stdout.write(outcome + "\n");
  await call("Browser.close").catch(() => {});
} catch (error) {
  process.stderr.write(error.message + "\n");
  process.exitCode = 1;
} finally {
  socket?.close();
  browser.kill();
  await Promise.race([exited, pause(3000)]);
  await pause(100);
}
