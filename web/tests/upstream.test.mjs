import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { once } from "node:events";
import { boundedJSON, fetchLocal } from "../lib/upstream.mjs";

test("bounded wire parsing preserves large money across chunks", async () => {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('{"paise":9007199'));
      controller.enqueue(new TextEncoder().encode("254740993}"));
      controller.close();
    },
  });
  assert.equal(
    (
      await boundedJSON(
        new Response(stream, {
          headers: { "content-type": "application/json" },
        }),
      )
    ).paise,
    "9007199254740993",
  );
});

test("streaming body limit applies without trusting content-length", async () => {
  let cancelled = false;
  const stream = new ReadableStream({
    pull(controller) {
      controller.enqueue(new Uint8Array(10));
    },
    cancel() {
      cancelled = true;
    },
  });
  await assert.rejects(
    boundedJSON(
      new Response(stream, {
        headers: { "content-type": "application/json", "content-length": "1" },
      }),
      15,
    ),
    /size/,
  );
  assert.equal(cancelled, true);
});

test("oversized declared length fails before reading", async () => {
  await assert.rejects(
    boundedJSON(
      new Response("{}", {
        headers: {
          "content-type": "application/json",
          "content-length": "999999999999999999",
        },
      }),
    ),
    /size/,
  );
});

test("non-JSON and invalid UTF-8 responses fail", async () => {
  await assert.rejects(boundedJSON(new Response("<html>error</html>")), /JSON/);
  await assert.rejects(
    boundedJSON(
      new Response(new Uint8Array([255]), {
        headers: { "content-type": "application/json" },
      }),
    ),
  );
});

test("real HTTP redirect is rejected without visiting its target", async () => {
  let followed = false;
  const server = createServer((request, response) => {
    if (request.url === "/redirect") {
      response.writeHead(302, { Location: "/target" });
      response.end();
    } else {
      followed = true;
      response.end("{}");
    }
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    await assert.rejects(
      fetchLocal(
        `http://127.0.0.1:${server.address().port}/redirect`,
        "unit-test-only",
      ),
    );
    assert.equal(followed, false);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
