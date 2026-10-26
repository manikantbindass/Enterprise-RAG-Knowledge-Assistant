import { strict as assert } from "node:assert";
import { test } from "node:test";
import { readStream } from "../src/lib/runtime";

test("SSE parser preserves split UTF-8 characters and packet boundaries", async () => {
  const encoded = new TextEncoder().encode(
    'event: token\ndata: "Hello 🌍"\n\nevent: done\ndata: {"status":"completed"}\n\n',
  );
  const response = new Response(
    new ReadableStream({
      start(controller) {
        for (const byte of encoded) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      },
    }),
  );
  const events: [string, unknown][] = [];
  await readStream(response, (event, data) => events.push([event, data]));
  assert.deepEqual(events, [
    ["token", "Hello 🌍"],
    ["done", { status: "completed" }],
  ]);
});

test("SSE parser rejects truncated streams and HTTP errors", async () => {
  await assert.rejects(
    readStream(new Response('event: token\ndata: "partial"\n\n'), () => {}),
    /ended early/,
  );
  await assert.rejects(
    readStream(
      new Response(JSON.stringify({ detail: "Session expired" }), {
        status: 401,
      }),
      () => {},
    ),
    /Session expired/,
  );
});

test("SSE parser accepts CRLF and structured errors", async () => {
  const events: string[] = [];
  const encoded = new TextEncoder().encode(
    'event: error\r\ndata: "Provider unavailable"\r\n\r\nevent: done\r\ndata: {}\r\n\r\n',
  );
  const response = new Response(
    new ReadableStream({
      start(controller) {
        for (const byte of encoded) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      },
    }),
  );
  await readStream(response, (event) => events.push(event));
  assert.deepEqual(events, ["error", "done"]);
});
