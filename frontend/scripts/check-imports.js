#!/usr/bin/env node
//
// Verifica se todo import relativo em um arquivo TS/JS *commitado* aponta
// para outro arquivo *commitado* — não apenas presente no disco local.
//
// Motivo: já aconteceu duas vezes de um arquivo existir localmente, nunca
// ter sido commitado, e um arquivo já commitado importá-lo — isso quebra o
// build via GitHub (Vercel), mas passa batido em `npm run build` local e em
// `tsc --noEmit`, já que ambos leem do disco, não do git.
//
// Lê o conteúdo de cada arquivo via `git show HEAD:<path>` (não do disco),
// então reflete exatamente o que um clone limpo do HEAD atual build gera —
// o mesmo método usado na auditoria manual que validou este script.

"use strict";

const { execSync } = require("child_process");
const path = require("path");

const EXTS = [".ts", ".tsx", ".js", ".jsx"];
const IMPORT_RE =
  /(?:import|export)\s+(?:[^'"]*?from\s+)?['"](\.[^'"]+)['"]|require\(\s*['"](\.[^'"]+)['"]\s*\)/g;

function sh(cmd, silent = false) {
  return execSync(cmd, {
    encoding: "utf8",
    maxBuffer: 1024 * 1024 * 64,
    stdio: silent ? ["pipe", "pipe", "pipe"] : undefined,
  });
}

const repoRoot = sh("git rev-parse --show-toplevel").trim();
process.chdir(repoRoot);

// Caminhos relativos à raiz do repo (não ao cwd), igual ao que
// `git show HEAD:<path>` espera.
const tracked = new Set(
  sh("git ls-files -- frontend").split("\n").filter(Boolean)
);

const sourceFiles = [...tracked].filter((f) => EXTS.includes(path.extname(f)));

function resolves(basePath) {
  const norm = basePath.split(path.sep).join("/");
  const candidates = [
    norm,
    ...EXTS.map((e) => norm + e),
    ...EXTS.map((e) => `${norm}/index${e}`),
  ];
  return candidates.some((c) => tracked.has(c));
}

const missing = [];
let checkedCount = 0;

for (const file of sourceFiles) {
  let content;
  try {
    content = sh(`git show HEAD:${JSON.stringify(file)}`, true);
  } catch {
    // Arquivo listado por `git ls-files` (inclui staged) mas ainda ausente
    // em HEAD (commit ainda não feito) — não é o caso que este script
    // audita, então pula sem barulho.
    continue;
  }

  let m;
  IMPORT_RE.lastIndex = 0;
  while ((m = IMPORT_RE.exec(content))) {
    const rel = m[1] || m[2];
    checkedCount++;
    const base = path.normalize(path.join(path.dirname(file), rel));
    if (!resolves(base)) {
      missing.push({ file, rel });
    }
  }
}

console.log(`Arquivos-fonte commitados verificados: ${sourceFiles.length}`);
console.log(`Imports relativos verificados: ${checkedCount}`);

if (missing.length > 0) {
  console.error(
    `\nIMPORTS QUEBRADOS — apontam para arquivo NÃO commitado (${missing.length}):`
  );
  for (const { file, rel } of missing) {
    console.error(`  ${file}  ->  ${rel}`);
  }
  process.exit(1);
}

console.log("\nNenhum import relativo quebrado encontrado (contra estado commitado).");
