#!/usr/bin/env node

/**
 * i18n lint script for TrustShield frontend.
 *
 * Scans all .tsx/.ts files under frontend/app and frontend/components for
 * t("...") calls, parses every locale catalog from frontend/messages/*.json,
 * and reports:
 *   - keys used in code but missing in a locale catalog
 *   - keys present in a catalog but never referenced in code
 *
 * Handles next-intl's useTranslations("namespace") scoping.
 * Exit code 1 if any issues are found.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join, basename } from "node:path";

const ROOT = join(import.meta.dirname, "..", "frontend");
const MESSAGES_DIR = join(ROOT, "messages");
const SCAN_DIRS = [join(ROOT, "app"), join(ROOT, "components")];
const FILE_PATTERN = /\.(tsx|ts|jsx|js)$/;

// ---------------------------------------------------------------------------
// 1. Collect all t("...") keys from source files
// ---------------------------------------------------------------------------

function walkDir(dir) {
  const results = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkDir(full));
    } else if (FILE_PATTERN.test(entry.name)) {
      results.push(full);
    }
  }
  return results;
}

const tCallRegex = /\bt\(\s*["'`]([^"'`]+)["'`]/g;
const namespaceRegex = /useTranslations\(\s*["'`]([^"'`]+)["'`]/g;

/** @returns Map<string, Set<string>>  key → set of file paths using it */
function collectUsedKeys() {
  const used = new Map();
  for (const dir of SCAN_DIRS) {
    for (const file of walkDir(dir)) {
      const content = readFileSync(file, "utf-8");

      // Detect useTranslations("namespace") calls
      const namespaces = new Set();
      let nsMatch;
      const nsRe = new RegExp(namespaceRegex.source, "g");
      while ((nsMatch = nsRe.exec(content)) !== null) {
        namespaces.add(nsMatch[1]);
      }

      // Extract t() call keys
      let match;
      const tRe = new RegExp(tCallRegex.source, "g");
      while ((match = tRe.exec(content)) !== null) {
        const raw = match[1];

        // Handle namespaced keys like "common:demoMode"
        const colonIdx = raw.indexOf(":");
        if (colonIdx >= 0) {
          const ns = raw.slice(0, colonIdx);
          const key = raw.slice(colonIdx + 1);
          const fullKey = `${ns}.${key}`;
          if (!used.has(fullKey)) used.set(fullKey, new Set());
          used.get(fullKey).add(file);
          continue;
        }

        // If file has useTranslations("ns"), resolve to ns.key
        if (namespaces.size === 1) {
          const ns = [...namespaces][0];
          const fullKey = `${ns}.${raw}`;
          if (!used.has(fullKey)) used.set(fullKey, new Set());
          used.get(fullKey).add(file);
        } else if (namespaces.size > 1) {
          // Multiple namespaces — try each one
          for (const ns of namespaces) {
            const fullKey = `${ns}.${raw}`;
            if (!used.has(fullKey)) used.set(fullKey, new Set());
            used.get(fullKey).add(file);
          }
        } else {
          // No useTranslations found — bare key
          if (!used.has(raw)) used.set(raw, new Set());
          used.get(raw).add(file);
        }
      }
    }
  }
  return used;
}

// ---------------------------------------------------------------------------
// 2. Parse locale catalogs
// ---------------------------------------------------------------------------

/** Flatten nested JSON into dot-separated keys: { a: { b: 1 } } → "a.b" */
function flatten(obj, prefix = "") {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      Object.assign(out, flatten(v, path));
    } else {
      out[path] = v;
    }
  }
  return out;
}

/** @returns Map<string, Record<string, string>>  locale → (flat-key → value) */
function loadLocaleFiles() {
  const files = readdirSync(MESSAGES_DIR).filter((f) => f.endsWith(".json"));
  const catalogs = new Map();
  for (const file of files) {
    const locale = basename(file, ".json");
    const raw = JSON.parse(readFileSync(join(MESSAGES_DIR, file), "utf-8"));
    catalogs.set(locale, flatten(raw));
  }
  return catalogs;
}

// ---------------------------------------------------------------------------
// 3. Compare
// ---------------------------------------------------------------------------

const usedKeys = collectUsedKeys();
const catalogs = loadLocaleFiles();
const defaultLocale = "en";

let hasIssues = false;

for (const [locale, keys] of catalogs) {
  const usedSet = new Set(usedKeys.keys());
  const catalogSet = new Set(Object.keys(keys));

  const missing = [...usedSet].filter((k) => !catalogSet.has(k));
  const unused = [...catalogSet].filter((k) => !usedSet.has(k));

  if (missing.length > 0) {
    hasIssues = true;
    console.error(`\n  [${locale}] Missing keys (used in code but not in catalog):`);
    for (const key of missing.sort()) {
      const files = [...usedKeys.get(key)];
      console.error(`    ${key}`);
      for (const f of files) {
        console.error(`      <- ${f}`);
      }
    }
  }

  if (unused.length > 0) {
    hasIssues = hasIssues || locale === defaultLocale;
    const level = locale === defaultLocale ? "error" : "warn";
    const log = level === "error" ? console.error : console.warn;
    log(`\n  [${locale}] Unused keys (in catalog but never referenced in code):`);
    for (const key of unused.sort()) {
      log(`    ${key}`);
    }
  }

  if (missing.length === 0 && unused.length === 0) {
    console.log(`  [${locale}] All keys in sync`);
  }
}

// ---------------------------------------------------------------------------
// 4. Cross-locale comparison
// ---------------------------------------------------------------------------

const locales = [...catalogs.keys()];
if (locales.length > 1) {
  const defaultKeys = catalogs.get(defaultLocale) ?? {};
  for (const locale of locales) {
    if (locale === defaultLocale) continue;
    const otherKeys = catalogs.get(locale);
    const missingInOther = Object.keys(defaultKeys).filter((k) => !(k in otherKeys));
    const extraInOther = Object.keys(otherKeys).filter((k) => !(k in defaultKeys));

    if (missingInOther.length > 0) {
      hasIssues = true;
      console.error(
        `\n  [${locale}] Keys present in ${defaultLocale} but missing:`
      );
      for (const key of missingInOther.sort()) {
        console.error(`    ${key}`);
      }
    }
    if (extraInOther.length > 0) {
      console.warn(
        `\n  [${locale}] Keys present in ${locale} but missing from ${defaultLocale}:`
      );
      for (const key of extraInOther.sort()) {
        console.warn(`    ${key}`);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Done
// ---------------------------------------------------------------------------

if (hasIssues) {
  console.error("\ni18n lint failed.\n");
  process.exit(1);
} else {
  console.log("\ni18n lint passed.\n");
}
