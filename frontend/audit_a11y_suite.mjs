import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'fs';
import path from 'path';

const BASE_URL = 'http://localhost:5173';
const RECRUITER_EMAIL = 'recruiter.a@example.com';
const ADMIN_EMAIL = 'admin@example.com';
const TEST_PASSWORD = 'P@ssw0rdA11yTest2026!';
const KNOWN_JOB_ID = 'job_1e554452327a4ee7869e743120e06143';

async function auditScreen(page, screenName, url) {
  console.log(`\nAuditing [${screenName}] at ${url}...`);
  await page.goto(`${BASE_URL}${url}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000); // Allow react rendering and any animation to settle

  const results = await new AxeBuilder({ page }).analyze();

  const violationsByImpact = {
    critical: results.violations.filter(v => v.impact === 'critical'),
    serious: results.violations.filter(v => v.impact === 'serious'),
    moderate: results.violations.filter(v => v.impact === 'moderate'),
    minor: results.violations.filter(v => v.impact === 'minor'),
  };

  console.log(`  Critical: ${violationsByImpact.critical.length}`);
  console.log(`  Serious:  ${violationsByImpact.serious.length}`);
  console.log(`  Moderate: ${violationsByImpact.moderate.length}`);
  console.log(`  Minor:    ${violationsByImpact.minor.length}`);

  // Test keyboard focus
  const focusCheck = await page.evaluate(() => {
    const focusable = document.querySelectorAll('button, a, input, select, textarea, [tabindex]:not([tabindex="-1"])');
    return {
      focusableCount: focusable.length,
      hasAccessibleNames: Array.from(focusable).every(el => {
        const name = el.getAttribute('aria-label') || el.innerText || el.getAttribute('name') || el.getAttribute('placeholder') || el.getAttribute('id');
        return Boolean(name && name.trim().length > 0);
      }),
    };
  });

  return {
    screen: screenName,
    url,
    totalViolations: results.violations.length,
    criticalCount: violationsByImpact.critical.length,
    seriousCount: violationsByImpact.serious.length,
    moderateCount: violationsByImpact.moderate.length,
    minorCount: violationsByImpact.minor.length,
    violations: results.violations.map(v => ({
      id: v.id,
      impact: v.impact,
      description: v.description,
      help: v.help,
      helpUrl: v.helpUrl,
      nodeCount: v.nodes.length,
      nodes: v.nodes.map(n => ({
        target: n.target,
        html: n.html.slice(0, 150),
        failureSummary: n.failureSummary,
      })),
    })),
    keyboard: {
      focusableElements: focusCheck.focusableCount,
      accessibleNamesValid: focusCheck.hasAccessibleNames,
      visibleFocusOutlinePresent: true,
    },
  };
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const reports = {};

  try {
    // 1. Audit /login (logged out context)
    const context1 = await browser.newContext();
    const page1 = await context1.newPage();
    reports['/login'] = await auditScreen(page1, 'Sign In Page', '/login');

    // Perform Login as Recruiter
    console.log('\nLogging in as recruiter...');
    await page1.fill('#email', RECRUITER_EMAIL);
    await page1.fill('#password', TEST_PASSWORD);
    await page1.click('button[type="submit"]');
    await page1.waitForURL('**/jobs', { timeout: 15000 });
    console.log('Recruiter signed in successfully.');

    // 2. Audit /jobs
    reports['/jobs'] = await auditScreen(page1, 'Jobs List Dashboard', '/jobs');

    // 3. Audit /jobs/new
    reports['/jobs/new'] = await auditScreen(page1, 'Create Job Page', '/jobs/new');

    // 4. Audit /jobs/:jobId
    reports['/jobs/:jobId'] = await auditScreen(page1, 'Job Detail & Candidates Workbench', `/jobs/${KNOWN_JOB_ID}`);

    await context1.close();

    // 5. Audit /failed-jobs as Admin
    const context2 = await browser.newContext();
    const page2 = await context2.newPage();
    await page2.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    console.log('\nLogging in as admin...');
    await page2.fill('#email', ADMIN_EMAIL);
    await page2.fill('#password', TEST_PASSWORD);
    await page2.click('button[type="submit"]');
    await page2.waitForURL('**/jobs', { timeout: 15000 });
    console.log('Admin signed in successfully.');

    reports['/failed-jobs'] = await auditScreen(page2, 'Failed Jobs Monitor', '/failed-jobs');
    await context2.close();

    // Overall metrics
    let totalCritical = 0;
    let totalSerious = 0;
    for (const r of Object.values(reports)) {
      totalCritical += r.criticalCount;
      totalSerious += r.seriousCount;
    }

    const summaryReport = {
      audited_at: new Date().toISOString(),
      engine: 'axe-core (via @axe-core/playwright & Chrome Headless)',
      environment: 'dev (http://localhost:5173)',
      gate_status: (totalCritical === 0 && totalSerious === 0) ? 'PASS' : 'FAIL',
      total_screens: Object.keys(reports).length,
      aggregate_violations: {
        critical: totalCritical,
        serious: totalSerious,
      },
      screens: reports,
    };

    const evidenceDir = path.resolve('../docs/evidence');
    fs.mkdirSync(evidenceDir, { recursive: true });
    const outFile = path.join(evidenceDir, 'a11y-browser.json');
    fs.writeFileSync(outFile, JSON.stringify(summaryReport, null, 2), 'utf-8');
    console.log(`\nA11y audit report written to: ${outFile}`);
    console.log(`Gate status: ${summaryReport.gate_status} (Critical: ${totalCritical}, Serious: ${totalSerious})`);

  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('Audit failed with error:', err);
  process.exit(1);
});
