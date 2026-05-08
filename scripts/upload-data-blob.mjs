import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { readFile, stat } from "node:fs/promises";
import { basename } from "node:path";
import { put } from "@vercel/blob";

function loadLocalEnv(path = ".env.local") {
  if (!existsSync(path)) {
    return;
  }

  for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match) {
      continue;
    }
    const [, key, rawValue] = match;
    if (process.env[key] !== undefined) {
      continue;
    }
    let value = rawValue.trim();
    if (
      (value.startsWith("\"") && value.endsWith("\"")) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value.replaceAll("\\n", "\n");
  }
}

loadLocalEnv();

const sourcePath = process.argv[2] ?? "backend/data/netkeiba_2026_enriched.csv";
const blobPath = process.argv[3] ?? `data/${basename(sourcePath)}`;

if (!process.env.BLOB_READ_WRITE_TOKEN) {
  console.error("BLOB_READ_WRITE_TOKEN is required. Link Vercel Blob and pull env first.");
  process.exit(1);
}

const [body, stats] = await Promise.all([readFile(sourcePath), stat(sourcePath)]);
const sha256 = createHash("sha256").update(body).digest("hex");

const blob = await put(blobPath, body, {
  access: "public",
  addRandomSuffix: false,
  allowOverwrite: true,
  contentType: sourcePath.endsWith(".csv") ? "text/csv; charset=utf-8" : "application/octet-stream",
});

const result = {
  url: blob.url,
  pathname: blob.pathname,
  size_bytes: stats.size,
  sha256,
  env: {
    UMALAB_HISTORY_CSV_URLS: blob.url,
    UMALAB_HISTORY_CSV_SHA256S: sha256,
  },
};

console.log(JSON.stringify(result, null, 2));
