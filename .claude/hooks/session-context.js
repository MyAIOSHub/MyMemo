#!/usr/bin/env node
/**
 * SessionStart hook — check memory-docs freshness, trigger materialization
 * if stale, then inject INDEX.md as initial context so Claude knows what
 * memory files are available.
 *
 * Input (stdin JSON): { cwd, ... }
 * Output (stdout JSON): { additionalContext, systemMessage? }
 */

import { readFileSync, existsSync, statSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { execSync } from "child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Resolve project root: walk up from cwd until we find memory-docs/ or memory-hub.env
function findProjectRoot() {
  let dir = process.cwd();
  for (let i = 0; i < 10; i++) {
    if (existsSync(resolve(dir, "memory-docs")) || existsSync(resolve(dir, "memory-hub.env"))) return dir;
    const parent = resolve(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }
  return process.cwd();
}

const PROJECT_ROOT = process.env.MEMORY_DOCS_ROOT || findProjectRoot();
const MEMORY_DOCS_DIR = resolve(PROJECT_ROOT, "memory-docs");
const MATERIALIZER_DIR = resolve(PROJECT_ROOT, "memory-hub-mcp");
const MEMORY_HUB_URL = process.env.MEMORY_HUB_URL || "http://localhost:1995";
const MAX_AGE_MINUTES = 30;

function isStale() {
  const marker = resolve(MEMORY_DOCS_DIR, ".last_materialized");
  if (!existsSync(marker)) return true;
  try {
    const ts = new Date(readFileSync(marker, "utf8").trim());
    const ageMs = Date.now() - ts.getTime();
    return ageMs > MAX_AGE_MINUTES * 60 * 1000;
  } catch {
    return true;
  }
}

async function hubIsAlive() {
  try {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 3000);
    const r = await fetch(`${MEMORY_HUB_URL}/health`, { signal: ac.signal });
    clearTimeout(t);
    return r.ok;
  } catch {
    return false;
  }
}

function runMaterializer() {
  try {
    execSync(
      `uv run --directory "${MATERIALIZER_DIR}" python materializer.py --output "${MEMORY_DOCS_DIR}"`,
      { timeout: 120_000, stdio: "ignore" }
    );
    return true;
  } catch {
    return false;
  }
}

async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;

  // Check if Memory Hub is alive
  const alive = await hubIsAlive();
  if (!alive) {
    // Hub down — if stale docs exist, use them anyway; otherwise skip
    if (!existsSync(resolve(MEMORY_DOCS_DIR, "INDEX.md"))) {
      process.exit(0);
    }
  }

  // Refresh if stale
  if (alive && isStale()) {
    runMaterializer();
  }

  // Read INDEX.md
  const indexPath = resolve(MEMORY_DOCS_DIR, "INDEX.md");
  if (!existsSync(indexPath)) process.exit(0);

  const indexContent = readFileSync(indexPath, "utf8").trim();
  if (!indexContent) process.exit(0);

  const output = {
    additionalContext: [
      "You have access to the following memory documents from past sessions.",
      "When the user asks about a specific project or topic, the relevant .md file",
      "will be automatically loaded via the UserPromptSubmit hook.",
      "",
      indexContent,
    ].join("\n"),
  };

  // Count files
  const fileCount = (indexContent.match(/\*\*\[/g) || []).length;
  if (fileCount > 0) {
    output.systemMessage = `Memory Hub: ${fileCount} knowledge documents available.`;
  }

  process.stdout.write(JSON.stringify(output));
}

main().catch(() => process.exit(0));
