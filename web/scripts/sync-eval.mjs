// Copies the committed benchmark results into the frontend so the public
// Evaluation page is rendered statically (no backend needed to read it).
import { copyFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../../eval/results.json");
const dest = resolve(here, "../lib/eval-results.json");
mkdirSync(dirname(dest), { recursive: true });
if (existsSync(src)) {
  copyFileSync(src, dest);
  console.log("sync-eval: copied eval/results.json");
} else if (!existsSync(dest)) {
  writeFileSync(dest, "null");
  console.log("sync-eval: no results yet; run `python -m privacytwin.eval`");
}
