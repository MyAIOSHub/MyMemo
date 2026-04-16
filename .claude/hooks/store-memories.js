#!/usr/bin/env node
/**
 * Stop hook — extract the last turn from the transcript and store it
 * as a memory in EverCore Memory Hub.
 *
 * Input (stdin JSON): { transcript_path, cwd, ... }
 * Output: none (fire-and-forget)
 *
 * Connects to local EverCore at MEMORY_HUB_URL (default http://localhost:1995).
 */

import { readFileSync, existsSync } from "fs";
import { createHash } from "crypto";

const MEMORY_HUB_URL = process.env.MEMORY_HUB_URL || "http://localhost:1995";
const MEMORY_HUB_USER_ID = process.env.MEMORY_HUB_USER_ID || "mymemo_user";
const TIMEOUT_MS = 30000;
const MAX_CONTENT_LENGTH = 20000;

function messageId(seed, role, content) {
  return "cc_" + createHash("sha256").update(`${seed}:${role}:${content}`).digest("hex").slice(0, 24);
}

/**
 * Extract the last turn's user input and assistant response from transcript.
 * A turn ends at a turn_duration system entry.
 */
function extractLastTurn(lines) {
  // Find the last turn boundary (turn_duration before current turn)
  let turnStart = 0;
  for (let i = lines.length - 1; i >= 0; i--) {
    try {
      const e = JSON.parse(lines[i]);
      if (e.type === "system" && e.subtype === "turn_duration") {
        turnStart = i + 1;
        break;
      }
    } catch {}
  }

  const userTexts = [];
  const assistantTexts = [];

  for (let i = turnStart; i < lines.length; i++) {
    try {
      const e = JSON.parse(lines[i]);
      const content = e.message?.content;

      if (e.type === "user") {
        if (typeof content === "string") {
          userTexts.push(content);
        } else if (Array.isArray(content)) {
          for (const block of content) {
            if (block.type === "text" && block.text) userTexts.push(block.text);
          }
        }
      }

      if (e.type === "assistant") {
        if (Array.isArray(content)) {
          for (const block of content) {
            if (block.type === "text" && block.text) assistantTexts.push(block.text);
          }
        } else if (typeof content === "string") {
          assistantTexts.push(content);
        }
      }
    } catch {}
  }

  return {
    user: userTexts.join("\n\n").trim().slice(0, MAX_CONTENT_LENGTH),
    assistant: assistantTexts.join("\n\n").trim().slice(0, MAX_CONTENT_LENGTH),
  };
}

async function storeMessages(messages, idSeed) {
  if (!messages.length) return;
  const stamp = Date.now();
  const items = messages.map((msg, i) => ({
    message_id: messageId(idSeed, msg.role, msg.content),
    sender_id: MEMORY_HUB_USER_ID,
    sender_name: msg.role === "assistant" ? "Claude Code" : MEMORY_HUB_USER_ID,
    role: msg.role,
    timestamp: stamp + i,
    content: msg.content,
  }));

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    await fetch(`${MEMORY_HUB_URL}/api/v1/memories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: MEMORY_HUB_USER_ID, messages: items }),
      signal: ac.signal,
    });
  } catch {
    // Silent failure — memory storage is best-effort.
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;

  const hookInput = JSON.parse(input);
  const transcriptPath = hookInput.transcript_path;

  if (!transcriptPath || !existsSync(transcriptPath)) {
    process.exit(0);
  }

  // Health check — skip if Memory Hub is down
  try {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 3000);
    const res = await fetch(`${MEMORY_HUB_URL}/health`, { signal: ac.signal });
    clearTimeout(t);
    if (!res.ok) process.exit(0);
  } catch {
    process.exit(0);
  }

  const content = readFileSync(transcriptPath, "utf8");
  const lines = content.trim().split("\n").filter(Boolean);

  const turn = extractLastTurn(lines);
  if (!turn.user && !turn.assistant) process.exit(0);

  const cwd = hookInput.cwd || process.cwd();
  const projectName = cwd.split("/").filter(Boolean).pop() || "unknown";
  const idSeed = `${projectName}:${Date.now()}`;

  const messages = [];
  if (turn.user) messages.push({ role: "user", content: turn.user });
  if (turn.assistant) messages.push({ role: "assistant", content: turn.assistant });

  await storeMessages(messages, idSeed);
}

main().catch(() => process.exit(0));
