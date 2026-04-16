#!/usr/bin/env node
/**
 * UserPromptSubmit hook — Intent Router
 *
 * 1. Read memory-docs/INDEX.md to get available .md files
 * 2. Call LLM to judge which .md files are relevant to the prompt
 * 3. Read selected .md files
 * 4. Inject their content as additionalContext
 *
 * Falls back to hybrid search if LLM/files unavailable.
 *
 * Input (stdin JSON): { prompt, cwd, ... }
 * Output (stdout JSON): { additionalContext, systemMessage }
 */

import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Resolve project root: walk up from cwd until we find memory-docs/ or .git
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
const ENV_FILE = resolve(PROJECT_ROOT, "memory-hub.env");

const MEMORY_HUB_URL = process.env.MEMORY_HUB_URL || "http://localhost:1995";
const MEMORY_HUB_USER_ID = process.env.MEMORY_HUB_USER_ID || "mymemo_user";
let LLM_API_KEY = process.env.LLM_API_KEY || "";
let LLM_BASE_URL = process.env.LLM_BASE_URL || "https://dashscope.aliyuncs.com/compatible-mode/v1";
let LLM_MODEL = process.env.LLM_MODEL || "qwen-long";

const MIN_WORDS = 3;
const MAX_MEMORIES_FALLBACK = 8;
const MIN_SCORE = 0.1;
const LLM_TIMEOUT_MS = 10000;
const SEARCH_TIMEOUT_MS = 10000;

// ---------------------------------------------------------------------------
// Load env from memory-hub.env if API key not already set
// ---------------------------------------------------------------------------
function loadEnv() {
  if (LLM_API_KEY) return;
  if (!existsSync(ENV_FILE)) return;
  for (const line of readFileSync(ENV_FILE, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 0) continue;
    const key = trimmed.slice(0, eq).trim();
    const val = trimmed.slice(eq + 1).trim();
    if (!process.env[key]) process.env[key] = val;
  }
  // Re-read after loading
  LLM_API_KEY = process.env.LLM_API_KEY || "";
  LLM_BASE_URL = process.env.LLM_BASE_URL || LLM_BASE_URL;
  LLM_MODEL = process.env.LLM_MODEL || LLM_MODEL;
}

function countTokens(text) {
  if (!text) return 0;
  const cjk = (text.match(/[\u4E00-\u9FFF\u3400-\u4DBF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF]/g) || []).length;
  const words = text.replace(/[\u4E00-\u9FFF\u3400-\u4DBF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF]/g, " ").trim().split(/\s+/).filter(Boolean).length;
  return cjk + words;
}

// ---------------------------------------------------------------------------
// Intent Router: LLM selects which .md files to read
// ---------------------------------------------------------------------------
async function intentRoute(prompt, indexContent) {
  const apiKey = process.env.LLM_API_KEY || LLM_API_KEY;
  const baseUrl = process.env.LLM_BASE_URL || LLM_BASE_URL;
  const model = process.env.LLM_MODEL || LLM_MODEL;

  if (!apiKey) return null;

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), LLM_TIMEOUT_MS);

  try {
    const res = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        messages: [
          {
            role: "system",
            content:
              "You are a memory router. Given available memory document files and a user prompt, " +
              "select ONLY the files directly relevant to the current task. " +
              "Return a JSON object: {\"files\": [\"file1.md\", \"file2.md\"]}. " +
              "Select 0-3 files. Select 0 if nothing is relevant. " +
              "Always include recent-focus.md if the prompt is about current/recent work.",
          },
          {
            role: "user",
            content: `Available files:\n${indexContent}\n\nUser prompt: ${prompt}`,
          },
        ],
        max_tokens: 200,
        temperature: 0,
      }),
      signal: ac.signal,
    });

    clearTimeout(timer);
    if (!res.ok) return null;

    let text = (await res.json()).choices?.[0]?.message?.content || "";
    text = text.trim();
    if (text.startsWith("```")) text = text.split("\n", 2)[1]?.split("```")[0] || text;
    const parsed = JSON.parse(text);
    return parsed.files || [];
  } catch {
    clearTimeout(timer);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Fallback: hybrid search (original behavior)
// ---------------------------------------------------------------------------
async function fallbackSearch(prompt) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), SEARCH_TIMEOUT_MS);
  try {
    const res = await fetch(`${MEMORY_HUB_URL}/api/v1/memories/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: prompt,
        method: "hybrid",
        memory_types: ["episodic_memory"],
        top_k: MAX_MEMORIES_FALLBACK,
        filters: { user_id: MEMORY_HUB_USER_ID },
      }),
      signal: ac.signal,
    });
    clearTimeout(timer);
    if (!res.ok) return [];
    const body = await res.json();
    return (body?.data?.episodes || []).filter((m) => (m.score ?? 0) >= MIN_SCORE);
  } catch {
    clearTimeout(timer);
    return [];
  }
}

function formatFallbackContext(memories) {
  const lines = memories.map((m) => {
    const subject = m.subject || "";
    const body = m.summary || m.episode || "";
    const text = subject ? `${subject}: ${body}` : body;
    return `  - ${text.replace(/[\r\n]+/g, " ").trim().slice(0, 200)}`;
  });
  return [
    "Reference memory from past sessions (fallback search results):",
    "<memory>",
    "  <episodic>",
    ...lines,
    "  </episodic>",
    "</memory>",
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  loadEnv();

  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  const data = JSON.parse(input);
  const prompt = data.prompt || "";

  if (countTokens(prompt) < MIN_WORDS) process.exit(0);

  // Try Intent Router path: INDEX.md → LLM select → read .md → inject
  const indexPath = resolve(MEMORY_DOCS_DIR, "INDEX.md");
  if (existsSync(indexPath)) {
    const indexContent = readFileSync(indexPath, "utf8");
    const selectedFiles = await intentRoute(prompt, indexContent);

    if (selectedFiles && selectedFiles.length > 0) {
      const parts = [];
      let filesRead = 0;
      for (const filename of selectedFiles.slice(0, 3)) {
        const filePath = resolve(MEMORY_DOCS_DIR, filename);
        if (existsSync(filePath)) {
          const content = readFileSync(filePath, "utf8").trim();
          if (content) {
            parts.push(content);
            filesRead++;
          }
        }
      }

      if (filesRead > 0) {
        const context = [
          "Memory context from past sessions (selected by intent):",
          "",
          ...parts,
        ].join("\n");

        process.stdout.write(
          JSON.stringify({
            additionalContext: context,
            systemMessage: `Memory: loaded ${selectedFiles.join(", ")} (${filesRead} files)`,
          })
        );
        return;
      }
    }
  }

  // Fallback: hybrid search
  const memories = await fallbackSearch(prompt);
  if (!memories.length) process.exit(0);

  process.stdout.write(
    JSON.stringify({
      additionalContext: formatFallbackContext(memories),
      systemMessage: `Memory: fallback search, injected ${memories.length} results`,
    })
  );
}

main().catch(() => process.exit(0));
