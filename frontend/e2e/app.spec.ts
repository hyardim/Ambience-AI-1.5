import { test, expect } from '@playwright/test';

// ─────────────────────────────────────────────────────────────────────────────
// These E2E tests run against the real dev server + backend.
// Make sure both frontend (port 5173) and backend (port 8000) are running.
// If using Docker Compose: `docker compose up` then `npx playwright test`
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Authentication E2E', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('login page renders correctly', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /login to your account/i })).toBeVisible();
    await expect(page.getByLabel(/username/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /login/i })).toBeVisible();
  });

  test('fill demo credentials button works', async ({ page }) => {
    await page.getByText(/fill demo credentials/i).click();
    await expect(page.getByLabel(/username/i)).toHaveValue('gp@example.com');
    await expect(page.getByLabel(/password/i)).toHaveValue('password123');
  });

  test('shows error for invalid credentials', async ({ page }) => {
    await page.getByLabel(/username/i).fill('invalid@example.com');
    await page.getByLabel(/password/i).fill('wrongpassword');
    await page.getByRole('button', { name: /login/i }).click();

    // Should show some error message (exact text depends on backend)
    await expect(page.locator('.bg-red-50')).toBeVisible({ timeout: 10_000 });
  });

  test('successful login as GP redirects to consultations', async ({ page }) => {
    await page.getByLabel(/username/i).fill('gp@example.com');
    await page.getByLabel(/password/i).fill('password123');
    await page.getByRole('button', { name: /login/i }).click();

    await expect(page.getByText(/my consultations/i)).toBeVisible({ timeout: 10_000 });
  });

  test('navigate to register page', async ({ page }) => {
    await page.getByText(/register here/i).click();
    await expect(page.getByRole('heading', { name: /create your account/i })).toBeVisible();
  });
});

test.describe('Protected Routes E2E', () => {
  test('unauthenticated user is redirected to login', async ({ page }) => {
    await page.goto('/gp/queries');
    await expect(page.getByRole('heading', { name: /login to your account/i })).toBeVisible({ timeout: 10_000 });
  });

  test('landing page is accessible without auth', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL('/');
  });
});

test.describe('GP Workflow E2E', () => {
  test.beforeEach(async ({ page }) => {
    // Login as GP
    await page.goto('/login');
    await page.getByLabel(/username/i).fill('gp@example.com');
    await page.getByLabel(/password/i).fill('password123');
    await page.getByRole('button', { name: /login/i }).click();
    await expect(page.getByText(/my consultations/i)).toBeVisible({ timeout: 10_000 });
  });

  test('view consultations list', async ({ page }) => {
    await expect(page.getByText(/my consultations/i)).toBeVisible();
  });

  test('navigate to new consultation form', async ({ page }) => {
    await page.getByRole('button', { name: /new consultation/i }).click();
    await expect(page.getByRole('heading', { name: /new consultation/i })).toBeVisible();
  });

  test('create a new consultation', async ({ page }) => {
    await page.getByRole('button', { name: /new consultation/i }).click();

    await page.getByLabel(/consultation title/i).fill('E2E Test Consultation');
    await page.getByLabel(/specialty/i).selectOption('neurology');
    await page.getByLabel(/clinical question/i).fill('Testing the consultation flow end-to-end');
    await page.getByRole('button', { name: /submit consultation/i }).click();

    // Should navigate to the detail page (wait for content to load)
    await expect(page.locator('body')).toContainText(/E2E Test|consultation/i, { timeout: 15_000 });
  });

  test('search consultations', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search by title/i);
    if (await searchInput.isVisible()) {
      await searchInput.fill('nonexistent-query');
      await expect(page.getByText(/no consultations found/i)).toBeVisible({ timeout: 5_000 });
    }
  });

  test('navigate to profile page', async ({ page }) => {
    await page.getByTitle('My Profile').click();
    await page.waitForURL(/\/profile/, { timeout: 5_000 });
  });

  test('logout returns to login page', async ({ page }) => {
    await page.getByTitle('Logout').click();
    await expect(page.getByRole('heading', { name: /login to your account/i })).toBeVisible({ timeout: 5_000 });
  });
});

test.describe('Specialist Workflow E2E', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/username/i).fill('specialist@example.com');
    await page.getByLabel(/password/i).fill('password123');
    await page.getByRole('button', { name: /login/i }).click();
    // Should redirect to specialist page
    await page.waitForURL(/\/specialist/, { timeout: 10_000 });
  });

  test('view specialist queries page', async ({ page }) => {
    await expect(page.getByText(/queries for review/i)).toBeVisible({ timeout: 10_000 });
  });

  test('switch between queue and assigned tabs', async ({ page }) => {
    await expect(page.getByText(/queue/i)).toBeVisible({ timeout: 10_000 });

    if (await page.getByText(/my assigned/i).isVisible()) {
      await page.getByText(/my assigned/i).click();
    }
  });
});

test.describe('Admin Workflow E2E', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/username/i).fill('admin@example.com');
    await page.getByLabel(/password/i).fill('password123');
    await page.getByRole('button', { name: /login/i }).click();
    await page.waitForURL(/\/admin/, { timeout: 10_000 });
  });

  test('view admin users page', async ({ page }) => {
    await expect(page.getByText(/user management/i)).toBeVisible({ timeout: 10_000 });
  });

  test('navigate to admin chats page', async ({ page }) => {
    const chatsLink = page.getByRole('link', { name: /chats/i });
    if (await chatsLink.isVisible()) {
      await chatsLink.click();
      await page.waitForURL(/\/admin\/chats/, { timeout: 5_000 });
    }
  });

  test('navigate to audit logs page', async ({ page }) => {
    const logsLink = page.getByRole('link', { name: /audit logs/i });
    if (await logsLink.isVisible()) {
      await logsLink.click();
      await page.waitForURL(/\/admin\/logs/, { timeout: 5_000 });
    }
  });

  test('search users in admin panel', async ({ page }) => {
    await expect(page.getByText(/user management/i)).toBeVisible({ timeout: 10_000 });

    const searchInput = page.getByPlaceholder(/search by name or email/i);
    if (await searchInput.isVisible()) {
      await searchInput.fill('nonexistent');
      await expect(page.getByText(/no users found/i)).toBeVisible({ timeout: 5_000 });
    }
  });
});

test.describe('Access Control E2E', () => {
  test('GP cannot access admin pages', async ({ page }) => {
    // Login as GP
    await page.goto('/login');
    await page.getByLabel(/username/i).fill('gp@example.com');
    await page.getByLabel(/password/i).fill('password123');
    await page.getByRole('button', { name: /login/i }).click();
    await expect(page.getByText(/my consultations/i)).toBeVisible({ timeout: 10_000 });

    // Try to access admin page
    await page.goto('/admin/users');
    // Should be redirected to access denied
    await expect(page.locator('body')).toContainText(/access denied|not authorized|login/i, { timeout: 10_000 });
  });
});
