// Explicit credential-free local preview; never a fallback for API failures.
process.env.NEMO_PUBLIC_DEMO = "1";
process.argv = [
  process.argv[0],
  "next",
  "start",
  "--hostname",
  "127.0.0.1",
  "--port",
  "3002",
];
await import("next/dist/bin/next");
