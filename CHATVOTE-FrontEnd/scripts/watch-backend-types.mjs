/**
 * Watch backend model files and auto-regenerate TypeScript types.
 *
 * Uses Node.js built-in fs.watch (recursive on macOS) with debouncing.
 * Intended to run alongside `next dev`.
 */

import { watch } from "node:fs";
import { execSync } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const MODELS_DIR = resolve(__dirname, "../../CHATVOTE-BackEnd/src/models");
const FE_DIR = resolve(__dirname, "..");

let debounceTimer = null;
let isGenerating = false;

function regenerate() {
  if (isGenerating) return;
  isGenerating = true;
  const start = Date.now();
  try {
    execSync("node scripts/generate-types.mjs", {
      cwd: FE_DIR,
      stdio: "pipe",
      shell: "/bin/bash",
      timeout: 30_000,
    });
    const ms = Date.now() - start;
    console.log(`[watch-types] Regenerated in ${ms}ms`);
  } catch (err) {
    console.error("[watch-types] Generation failed:", err.stderr?.toString() || err.message);
  } finally {
    isGenerating = false;
  }
}

function onFileChange(eventType, filename) {
  if (!filename?.endsWith(".py")) return;

  console.log(`[watch-types] ${filename} changed, regenerating...`);

  // Debounce: wait 300ms for batch saves to settle
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(regenerate, 300);
}

console.log(`[watch-types] Watching ${MODELS_DIR}`);
watch(MODELS_DIR, { recursive: true }, onFileChange);
