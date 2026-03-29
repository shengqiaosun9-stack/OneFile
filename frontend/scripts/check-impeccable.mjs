#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const ROOT = process.cwd();
const RULES_PATH = path.join(ROOT, "impeccable", "gate.rules.json");
const BASELINE_PATH = path.join(ROOT, "impeccable", "baseline.json");
const BASELINE_REPORT_PATH = path.join(ROOT, "impeccable", "baseline-report.json");
const REPORT_PATH = path.join(ROOT, "test-results", "impeccable-report.json");
const UPDATE_BASELINE = process.argv.includes("--update-baseline");

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function ensureDir(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function issueFingerprint(issue) {
  return `${issue.id}|${issue.file}|${issue.selector}|${issue.message}`;
}

function pushIssue(issues, issue) {
  issues.push({
    severity: "error",
    ...issue,
  });
}

function checkRequiredTokens(issues, rule) {
  const filePath = path.join(ROOT, rule.file);
  if (!fs.existsSync(filePath)) {
    pushIssue(issues, {
      id: "missing-file",
      file: rule.file,
      selector: "file",
      message: "Target file does not exist.",
    });
    return;
  }
  const content = readText(filePath);
  for (const token of rule.required_tokens || []) {
    if (!content.includes(token)) {
      pushIssue(issues, {
        id: "missing-required-token",
        file: rule.file,
        selector: token,
        message: `Required token not found: ${token}`,
      });
    }
  }
}

function checkCssRules(issues, cssRule) {
  const filePath = path.join(ROOT, cssRule.file);
  if (!fs.existsSync(filePath)) {
    pushIssue(issues, {
      id: "missing-css-file",
      file: cssRule.file,
      selector: "file",
      message: "CSS file does not exist.",
    });
    return;
  }
  const content = readText(filePath);
  for (const snippet of cssRule.required_snippets || []) {
    if (!content.includes(snippet)) {
      pushIssue(issues, {
        id: "missing-css-snippet",
        file: cssRule.file,
        selector: snippet,
        message: `Required CSS snippet not found: ${snippet}`,
      });
    }
  }
}

function checkForbiddenPatterns(issues, patternRule) {
  const regex = new RegExp(patternRule.pattern, patternRule.flags || "");
  for (const relPath of patternRule.paths || []) {
    const filePath = path.join(ROOT, relPath);
    if (!fs.existsSync(filePath)) continue;
    const content = readText(filePath);
    if (regex.test(content)) {
      pushIssue(issues, {
        id: patternRule.id || "forbidden-pattern",
        file: relPath,
        selector: patternRule.selector || "content",
        message: patternRule.description || `Forbidden pattern matched: ${patternRule.pattern}`,
      });
    }
  }
}

function checkHexPalette(issues, allowedHexColors) {
  const cssPath = path.join(ROOT, "src", "app", "globals.css");
  if (!fs.existsSync(cssPath)) return;
  const css = readText(cssPath);
  const matches = css.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
  const normalizedAllowed = new Set((allowedHexColors || []).map((item) => item.toLowerCase()));
  for (const hex of matches) {
    const key = hex.toLowerCase();
    if (!normalizedAllowed.has(key)) {
      pushIssue(issues, {
        id: "disallowed-hex-color",
        file: "src/app/globals.css",
        selector: key,
        message: `Hex color is not in allowed palette: ${key}`,
      });
    }
  }
}

function loadBaseline() {
  if (!fs.existsSync(BASELINE_PATH)) {
    return { version: "1.0.0", fingerprints: [] };
  }
  return readJson(BASELINE_PATH);
}

function saveBaseline(report) {
  const fingerprints = report.issues.map((issue) => issueFingerprint(issue)).sort();
  ensureDir(BASELINE_PATH);
  fs.writeFileSync(
    BASELINE_PATH,
    JSON.stringify(
      {
        version: "1.0.0",
        updated_at: new Date().toISOString(),
        fingerprints,
      },
      null,
      2,
    ) + "\n",
  );
  fs.writeFileSync(
    BASELINE_REPORT_PATH,
    JSON.stringify(
      {
        generated_at: report.generated_at,
        issue_count: report.issue_count,
        issues: report.issues,
      },
      null,
      2,
    ) + "\n",
  );
}

function buildReport(issues, baseline) {
  const current = issues.map((issue) => issueFingerprint(issue));
  const baselineSet = new Set((baseline.fingerprints || []).map((item) => String(item)));
  const currentSet = new Set(current);

  const newIssues = issues.filter((issue) => !baselineSet.has(issueFingerprint(issue)));
  const resolvedCount = [...baselineSet].filter((fingerprint) => !currentSet.has(fingerprint)).length;

  return {
    generated_at: new Date().toISOString(),
    issue_count: issues.length,
    new_issue_count: newIssues.length,
    resolved_issue_count: resolvedCount,
    issues,
    new_issues: newIssues,
  };
}

function printReport(report) {
  if (report.issue_count === 0) {
    console.log("✅ impeccable gate passed: no issues found.");
    return;
  }

  if (report.new_issue_count === 0) {
    console.log(`⚠️ impeccable gate: ${report.issue_count} known baseline issue(s), no new regressions.`);
    return;
  }

  console.error(`❌ impeccable gate failed: ${report.new_issue_count} new issue(s), ${report.issue_count} total.`);
  for (const issue of report.new_issues) {
    console.error(` - [${issue.id}] ${issue.file} :: ${issue.selector} -> ${issue.message}`);
  }
}

function main() {
  if (!fs.existsSync(RULES_PATH)) {
    throw new Error(`Rules file not found: ${RULES_PATH}`);
  }
  const rules = readJson(RULES_PATH);
  const issues = [];

  for (const target of rules.targets || []) {
    checkRequiredTokens(issues, target);
  }
  if (rules.css) {
    checkCssRules(issues, rules.css);
  }
  for (const forbidden of rules.forbidden_patterns || []) {
    checkForbiddenPatterns(issues, forbidden);
  }
  checkHexPalette(issues, rules.allow_hex_colors || []);

  const baseline = loadBaseline();
  const report = buildReport(issues, baseline);

  ensureDir(REPORT_PATH);
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2) + "\n");

  if (UPDATE_BASELINE) {
    saveBaseline(report);
    console.log("✅ impeccable baseline updated.");
    printReport(report);
    return;
  }

  printReport(report);
  if (report.new_issue_count > 0) {
    process.exit(1);
  }
}

main();
