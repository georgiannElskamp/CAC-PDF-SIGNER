const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function until(probe, message, timeout = 90000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await probe();
    if (value) return value;
    await delay(500);
  }
  throw new Error(message);
}

async function connect(port, selectPage, ready) {
  const page = await until(async () => {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(2000) });
      return (await response.json()).find(selectPage);
    } catch (_) { return null; }
  }, "The PDF editor did not open.");
  const socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let sequence = 0;
  const pending = new Map(), contexts = new Set();
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.method === "Runtime.executionContextCreated") contexts.add(message.params.context.id);
    if (message.method === "Runtime.executionContextDestroyed") contexts.delete(message.params.executionContextId);
    const request = pending.get(message.id);
    if (request) {
      pending.delete(message.id);
      clearTimeout(request.timer);
      message.error ? request.reject(new Error(message.error.message)) : request.resolve(message.result);
    }
  };
  function call(method, params) {
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out`)); }, 125000);
      pending.set(id, { resolve, reject, timer });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(contextId, expression) {
    const reply = await call("Runtime.evaluate", { contextId, expression, awaitPromise: true, returnByValue: true, timeout: 120000 });
    if (reply.exceptionDetails) throw new Error(reply.exceptionDetails.exception?.description || reply.exceptionDetails.text);
    return reply.result.value;
  }
  try {
    await call("Runtime.enable");
    const context = await until(async () => {
      for (const id of contexts) {
        try {
          if (await evaluate(id, ready)) return id;
        } catch (error) {
          if (!/context.*(find|destroy)|find.*context/i.test(error.message)) throw error;
        }
      }
      return null;
    }, "The PDF editor context is unavailable (startup or harness failure).");
    const run = (fn, ...args) => evaluate(context, `(${fn.toString()})(${args.map((a) => JSON.stringify(a)).join(",")})`);
    return {
      page, call, run,
      close() {
        socket.close();
        for (const request of pending.values()) clearTimeout(request.timer);
        pending.clear();
      },
    };
  } catch (error) {
    socket.close();
    for (const request of pending.values()) clearTimeout(request.timer);
    throw error;
  }
}

module.exports = { connect, until };
