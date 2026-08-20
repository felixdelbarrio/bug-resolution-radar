#!/usr/bin/env node

import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { renderWebapp, validateRenderedWebapp } from "./run_webapp_local.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const APPS_SCRIPT = resolve(ROOT, "apps-script");

const files = readdirSync(APPS_SCRIPT).sort();
const gsFiles = files.filter((name) => name.endsWith(".gs"));
const htmlFiles = files.filter((name) => name.endsWith(".html"));
const source = (name) => readFileSync(resolve(APPS_SCRIPT, name), "utf8");

const serverCode = gsFiles.map(source).join("\n");
new vm.Script(serverCode, { filename: "apps-script:server-bundle" });

const declarations = new Map();
for (const name of gsFiles) {
  for (const match of source(name).matchAll(/^function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(/gm)) {
    const owners = declarations.get(match[1]) || [];
    owners.push(name);
    declarations.set(match[1], owners);
  }
}
const duplicates = [...declarations.entries()].filter(([, owners]) => owners.length > 1);
if (duplicates.length) {
  throw new Error(`Funciones globales duplicadas: ${JSON.stringify(duplicates)}`);
}

for (const name of htmlFiles) {
  const content = source(name);
  for (const [index, match] of [...content.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].entries()) {
    if (!match[1].includes("<?")) {
      new vm.Script(match[1], { filename: `${name}:inline-${index + 1}` });
    }
  }
}

const manifest = JSON.parse(source("appsscript.json"));
if (manifest.webapp?.access !== "DOMAIN" || manifest.webapp?.executeAs !== "USER_DEPLOYING") {
  throw new Error("appsscript.json debe conservar acceso DOMAIN y ejecución USER_DEPLOYING.");
}
if (manifest.runtimeVersion !== "V8") {
  throw new Error("Apps Script debe usar runtime V8.");
}

const config = source("00_Config.gs");
for (const expected of [
  "transferVersion: 3",
  "projectionVersion: 3",
  "semanticContract: 'desktop-authoritative-v3'"
]) {
  if (!config.includes(expected)) throw new Error(`Falta el contrato GPC: ${expected}`);
}

const runtimeFiles = files.filter((name) =>
  !["BrandAssets.html", "90_Setup.gs"].includes(name)
);
const runtime = runtimeFiles.map(source).join("\n").toLowerCase();
for (const retired of ["kanban", "opshealth", "salud operativa", "gemini"]) {
  if (runtime.includes(retired)) throw new Error(`Referencia runtime retirada detectada: ${retired}`);
}
const newsletter = source("56_Newsletter.gs").toLowerCase();
if (newsletter.includes("urlfetchapp")) {
  throw new Error("La newsletter no puede invocar servicios generativos o HTTP externos.");
}

const shellSource = source("Index.html");
const appSource = source("App.html");
const shellContract = appSource.match(
  /const REQUIRED_SHELL_IDS = Object\.freeze\(\[([\s\S]*?)\]\);/
);
if (!shellContract) {
  throw new Error("App.html debe declarar el contrato REQUIRED_SHELL_IDS.");
}
const requiredShellIds = [...shellContract[1].matchAll(/'([^']+)'/g)].map(
  (match) => match[1]
);
const declaredShellIds = new Set(
  [...shellSource.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1])
);
const missingShellIds = requiredShellIds.filter((id) => !declaredShellIds.has(id));
if (missingShellIds.length) {
  throw new Error(
    `Index.html no satisface el contrato de arranque: ${missingShellIds.join(", ")}`
  );
}

const renderedWebapp = renderWebapp();
validateRenderedWebapp(renderedWebapp);
console.log(
  `GPC quality gate OK: ${gsFiles.length} archivos GS, ${htmlFiles.length} HTML, ` +
  `${requiredShellIds.length} nodos de arranque y WebApp local v3.`
);
