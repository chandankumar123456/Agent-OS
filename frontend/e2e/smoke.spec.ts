import { test, expect } from '@playwright/test';

const TEST_USER = {
  email: `e2e-${Date.now()}@agentos.example.com`,
  password: 'E2ETestPass123!',
  name: 'E2E Test User',
};

test.describe('AgentOS Smoke Tests', () => {
  test('landing page loads without errors', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/AgentOS/i);
    await expect(page.locator('text=Get Started')).toBeVisible();
    // Verify no console errors
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
  });

  test('navigation from landing to login works', async ({ page }) => {
    await page.goto('/');
    await page.click('text=Sign In');
    await expect(page).toHaveURL(/.*login/);
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test('signup flow creates account and redirects to dashboard', async ({ page }) => {
    await page.goto('/signup');
    await page.fill('input[name="name"]', TEST_USER.name);
    await page.fill('input[name="email"]', TEST_USER.email);
    await page.fill('input[name="password"]', TEST_USER.password);
    await page.click('button[type="submit"]');
    // Should redirect to dashboard after successful signup
    await expect(page).toHaveURL(/.*dashboard/, { timeout: 10000 });
    await expect(page.locator('text=Dashboard')).toBeVisible();
  });

  test('login flow authenticates and shows dashboard', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name="email"]', TEST_USER.email);
    await page.fill('input[name="password"]', TEST_USER.password);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/.*dashboard/, { timeout: 10000 });
    await expect(page.locator('text=Submit Task')).toBeVisible();
  });

  test('dashboard loads metrics and task list', async ({ page }) => {
    // Login first
    await page.goto('/login');
    await page.fill('input[name="email"]', TEST_USER.email);
    await page.fill('input[name="password"]', TEST_USER.password);
    await page.click('button[type="submit"]');
    await page.waitForURL(/.*dashboard/, { timeout: 10000 });

    // Verify dashboard elements
    await expect(page.locator('text=Active Tasks')).toBeVisible();
    await expect(page.locator('text=Success Rate')).toBeVisible();
    await expect(page.locator('text=Avg Duration')).toBeVisible();
    await expect(page.locator('text=Tools Available')).toBeVisible();
  });

  test('task creation form is accessible', async ({ page }) => {
    // Login first
    await page.goto('/login');
    await page.fill('input[name="email"]', TEST_USER.email);
    await page.fill('input[name="password"]', TEST_USER.password);
    await page.click('button[type="submit"]');
    await page.waitForURL(/.*dashboard/, { timeout: 10000 });

    // Verify task input exists
    await expect(page.locator('textarea[placeholder*="task"]')).toBeVisible();
    await expect(page.locator('button:has-text("Submit Task")')).toBeVisible();
  });

  test('logout clears session and redirects to landing', async ({ page }) => {
    // Login first
    await page.goto('/login');
    await page.fill('input[name="email"]', TEST_USER.email);
    await page.fill('input[name="password"]', TEST_USER.password);
    await page.click('button[type="submit"]');
    await page.waitForURL(/.*dashboard/, { timeout: 10000 });

    // Logout
    await page.click('text=Logout');
    await expect(page).toHaveURL('/');
    await expect(page.locator('text=Get Started')).toBeVisible();
  });
});
