import { exactJSON } from "./contracts.mjs";

export const MAX_RESPONSE_BYTES = 8 * 1024 * 1024;

export async function boundedJSON(response, limit = MAX_RESPONSE_BYTES) {
  if (
    response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !==
    "application/json"
  ) {
    await response.body?.cancel();
    throw new Error("Expected JSON response");
  }
  const declared = response.headers.get("content-length");
  if (
    declared !== null &&
    (!/^\d+$/.test(declared) || BigInt(declared) > BigInt(limit))
  ) {
    await response.body?.cancel();
    throw new Error("Response size rejected");
  }
  if (!response.body) throw new Error("Missing response body");
  const reader = response.body.getReader();
  let size = 0;
  const chunks = [];
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) throw new Error("Response size rejected");
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return exactJSON(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
}

export function fetchLocal(url, token) {
  // Keep credentials on the exact configured endpoint, including same-origin redirects.
  return fetch(url, {
    headers: { Authorization: "Bearer " + token },
    redirect: "error",
    cache: "no-store",
    signal: AbortSignal.timeout(60000),
  });
}
