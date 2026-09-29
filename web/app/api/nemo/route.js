import { readFile } from "node:fs/promises";
import pathModule from "node:path";
import { exactJSON, apiPath, sameOrigin } from "../../../lib/contracts.mjs";
export const dynamic = "force-dynamic";
export async function GET(request) {
  if (!sameOrigin(request.headers))
    return Response.json({ error: "Local access required" }, { status: 403 });
  const url = new URL(request.url);
  let path;
  try {
    path = apiPath(
      url.searchParams.get("dataset"),
      url.searchParams.get("view"),
    );
  } catch {
    return Response.json({ error: "Unsupported request" }, { status: 400 });
  }
  if (process.env.NEMO_PUBLIC_DEMO === "1") {
    const dataset = url.searchParams.get("dataset"),
      view = url.searchParams.get("view");
    if (
      view !== "datasets" &&
      !["business", "healthy", "failure"].includes(dataset)
    )
      return Response.json(
        { error: "Dataset not in public lab preview" },
        { status: 404 },
      );
    const file =
      view === "datasets" ? "datasets.json" : dataset + "-" + view + ".json";
    try {
      return Response.json(
        exactJSON(
          await readFile(pathModule.join(process.cwd(), "demo", file), "utf8"),
        ),
      );
    } catch {
      return Response.json(
        { error: "Public lab export unavailable" },
        { status: 503 },
      );
    }
  }
  const base = process.env.NEMO_API_URL || "http://127.0.0.1:8000";
  if (
    !/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base) ||
    !process.env.NEMO_READ_TOKEN
  )
    return Response.json(
      { error: "Local API connection is not configured" },
      { status: 503 },
    );
  try {
    const response = await fetch(base + path, {
      headers: { Authorization: "Bearer " + process.env.NEMO_READ_TOKEN },
      cache: "no-store",
      signal: AbortSignal.timeout(60000),
    });
    if (!response.ok)
      return Response.json(
        {
          error: "Analysis unavailable",
          request_id: response.headers.get("x-request-id"),
        },
        { status: response.status },
      );
    return Response.json(exactJSON(await response.text()));
  } catch {
    return Response.json(
      {
        error:
          "Local API unavailable; check the server and dataset configuration",
      },
      { status: 503 },
    );
  }
}
