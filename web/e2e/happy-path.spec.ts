import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * Brief §14 happy path, entirely through the UI:
 * citizen lodges -> officer accepts the System Analysis -> work order ->
 * field team uploads an after-photo -> Evidence Auditor PASS -> Control Room
 * approves -> citizen confirms with 5 stars -> CLOSED.
 *
 * Each role uses its own browser context (its own session cookie).
 */

async function login(browser: Browser, username: string): Promise<Page> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto("/login");
  await page.getByLabel("User ID").fill(username);
  await page.getByRole("button", { name: "Get OTP" }).click();
  const otpText = await page.getByText(/^Demo OTP:/).locator("..").textContent();
  const otp = otpText?.match(/(\d{4,8})/)?.[1];
  expect(otp, "demo OTP shown on screen").toBeTruthy();
  await page.getByLabel("OTP", { exact: true }).fill(otp!);
  await page.getByRole("button", { name: "Verify and Login" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
  return page;
}

async function solveCaptcha(page: Page) {
  const q = await page.locator('label[for="captcha"]').textContent();
  const [, a, b] = q!.match(/(\d+)\s*\+\s*(\d+)/)!;
  await page.locator("#captcha").fill(String(Number(a) + Number(b)));
}

/** Reload until `text` appears (agents run in the background after an event). */
async function reloadUntil(page: Page, text: string | RegExp, timeoutMs = 60_000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    if (await page.getByText(text).first().isVisible().catch(() => false)) return;
    await page.waitForTimeout(2000);
    await page.reload();
  }
  await expect(page.getByText(text).first()).toBeVisible();
}

test("citizen lodges, officer accepts, field fixes, auditor passes, control approves, citizen closes", async ({
  browser,
}) => {
  const mobile = `9${String(Date.now()).slice(-9)}`;

  // 1. Citizen lodges a grievance (anonymous portal user, no login needed).
  const citizenCtx = await browser.newContext();
  const citizen = await citizenCtx.newPage();
  await citizen.goto("/lodge");
  await citizen.getByLabel("Category").selectOption("POTHOLE");
  await citizen
    .getByLabel("Description of the problem")
    .fill("E2E test: pothole near the bus shelter, two-wheelers swerving into traffic.");
  // Move the pin 100-250 m from the default so repeated runs are not merged as duplicates.
  const map = citizen.locator(".leaflet-container").first();
  const box = (await map.boundingBox())!;
  const dx = (Math.random() < 0.5 ? -1 : 1) * (90 + Math.random() * 60);
  const dy = (Math.random() < 0.5 ? -1 : 1) * (60 + Math.random() * 40);
  await map.click({ position: { x: box.width / 2 + dx, y: box.height / 2 + dy } });
  await citizen.getByLabel("Landmark").fill("E2E bus shelter");
  await citizen.getByLabel("Mobile number").fill(mobile);
  await citizen.getByLabel(/I declare that/).check();
  await citizen.getByLabel(/I agree that the Corporation/).check();
  await solveCaptcha(citizen);
  await citizen.getByRole("button", { name: "Submit" }).click();

  await expect(citizen.getByRole("heading", { name: "Acknowledgement Slip" })).toBeVisible();
  const grievanceNo = (await citizen.locator('th:text-is("Grievance No.") + td').textContent())!.trim();
  expect(grievanceNo).toMatch(/^SR-\d{4}-\d+$/);

  // 2. Ward officer reads the System Analysis and accepts it.
  const officer = await login(browser, "officer.w12");
  await officer.goto(`/officer/complaints/${grievanceNo}`);
  await reloadUntil(officer, "System Suggestion:");
  await officer.getByRole("button", { name: "Accept", exact: true }).click();
  await expect(officer.getByText("System suggestion accepted.")).toBeVisible();

  // 3. Officer creates a work order for crew W12-A.
  await officer.getByRole("button", { name: "Create work order" }).click();
  await officer.locator("select").filter({ has: officer.locator('option[value="W12-A"]') }).selectOption("W12-A");
  await officer.getByLabel("Scope of work").fill("E2E: fill pothole with cold-mix and compact.");
  await officer.getByRole("button", { name: "Create and assign" }).click();
  const woNotice = officer.getByText(/Work order WO-\S+ created/);
  await expect(woNotice).toBeVisible();
  const woId = (await woNotice.textContent())!.match(/(WO-[\d-]+)/)![1];

  // 4. Field team starts the job, uploads a correct after-photo and marks it completed.
  const field = await login(browser, "field.w12a");
  await field.goto(`/field/jobs/${woId}`);
  await field.getByRole("button", { name: "Start job" }).click();
  await expect(field.getByText("Job started.")).toBeVisible();
  const photo = await field.request.get(`/api/v1/demo/photos/after_good.jpg?wo_id=${woId}`);
  expect(photo.ok(), "demo photo endpoint (demo mode)").toBeTruthy();
  await field.getByLabel("Upload after photo").setInputFiles({
    name: `${woId}-after.jpg`,
    mimeType: "image/jpeg",
    buffer: await photo.body(),
  });
  await expect(field.getByText("After photo uploaded.")).toBeVisible();
  await field.getByRole("button", { name: "Mark completed" }).click();
  await expect(field.getByText(/Auto-check result: PASS/)).toBeVisible({ timeout: 60_000 });

  // 5. Control Room sees the auto-check result and approves.
  const control = await login(browser, "control");
  await control.goto("/control/verification");
  const panel = control.locator("section").filter({ hasText: woId });
  await expect(panel.getByText("PASS", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "Approve" }).click();
  await expect(control.getByText(`${woId} approved.`)).toBeVisible();

  // 6. Citizen tracks the grievance, sees it resolved, rates 5 stars and confirms.
  await citizen.goto("/track");
  await citizen.getByLabel("Grievance No.", { exact: true }).fill(grievanceNo);
  await citizen.getByLabel("Mobile number or tracking code").fill(mobile);
  await citizen.getByRole("button", { name: "Track", exact: true }).click();
  const statusCell = citizen.locator('th:text-is("Status") + td');
  await expect(statusCell).toHaveText(/Resolved/);
  await expect(citizen.getByRole("heading", { name: "After work" })).toBeVisible();
  await citizen.getByLabel("5 of 5").check({ force: true });
  await citizen.getByRole("button", { name: "Confirm Resolution" }).click();
  await expect(citizen.getByText("Thank you. Your confirmation has been recorded.")).toBeVisible();
  await expect(statusCell).toHaveText(/Closed/);
});
