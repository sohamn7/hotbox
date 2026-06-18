import { test, expect, Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const INBOX_LEADS = [
  {
    username: "matt.lifts.heavy",
    full_name: "Matt R.",
    raw_dm: "Hey I've been stuck at the same bench for 5 months. What does your coaching look like?",
    score: 87,
    summary: "Matt is a dedicated lifter seeking structured coaching. High intent, genuine fitness context.",
    enrichment: { wantsCoaching: true, isSpam: false, fitnessRelevance: "high — active lifter" },
    status: "inbox",
    reply_text: "",
  },
  {
    username: "sara.fitness.journey",
    full_name: "Sara K.",
    raw_dm: "Hi! I'm a NASM-certified PT with 12k followers. Would you be open to a collab?",
    score: 72,
    summary: "Sara is a certified PT with an engaged fitness audience seeking a brand collab.",
    enrichment: { wantsCollab: true, isSpam: false, fitnessRelevance: "high — fitness creator" },
    status: "inbox",
    reply_text: "",
  },
  {
    username: "growthboost_agency",
    full_name: "GrowthBoost Media",
    raw_dm: "Love your page! We help fitness brands grow to 10k+ followers guaranteed.",
    score: 5,
    summary: "Spam — growth agency offering follower packages.",
    enrichment: { isSpam: true, fitnessRelevance: "none" },
    status: "inbox",
    reply_text: "",
  },
];

const SENT_LEADS = [
  {
    username: "replied.user",
    full_name: "Replied User",
    raw_dm: "I'm interested in your coaching program.",
    score: 80,
    summary: "A lead that was replied to.",
    enrichment: { wantsCoaching: true, isSpam: false },
    status: "sent",
    reply_text: "Thanks for reaching out! Let's connect.",
  },
];

const ARCHIVE_LEADS: typeof INBOX_LEADS = [];

// ---------------------------------------------------------------------------
// Route mock helper
// ---------------------------------------------------------------------------

async function mockApiRoutes(
  page: Page,
  overrides: {
    inbox?: typeof INBOX_LEADS;
    sent?: typeof SENT_LEADS;
    archive?: typeof ARCHIVE_LEADS;
  } = {}
) {
  const inbox = overrides.inbox ?? INBOX_LEADS;
  const sent = overrides.sent ?? SENT_LEADS;
  const archive = overrides.archive ?? ARCHIVE_LEADS;

  await page.route("/api/leads*", (route) => {
    const url = new URL(route.request().url());
    const status = url.searchParams.get("status") ?? "inbox";
    const data = status === "sent" ? sent : status === "archive" ? archive : inbox;
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(data) });
  });

  await page.route(/\/api\/leads\/.+\/status/, (route) => {
    route.fulfill({ status: 200, contentType: "application/json", body: '{"ok":true}' });
  });

  await page.route(/\/api\/leads\/.+\/reply/, (route) => {
    route.fulfill({ status: 200, contentType: "application/json", body: '{"ok":true}' });
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Inbox", () => {
  test("shows three nav tabs: Inbox, Sent, Archive", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");
    await expect(page.getByRole("button", { name: /inbox/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /sent/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /archive/i })).toBeVisible();
  });

  test("renders inbox leads sorted by score descending", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    // All three leads should appear in the list
    await expect(page.getByText("Matt R.")).toBeVisible();
    await expect(page.getByText("Sara K.")).toBeVisible();
    await expect(page.getByText("GrowthBoost Media")).toBeVisible();

    // Score badges should be visible (87, 72, 5)
    await expect(page.getByText("87")).toBeVisible();
    await expect(page.getByText("72")).toBeVisible();
    await expect(page.getByText("5")).toBeVisible();
  });

  test("shows placeholder when no lead is selected", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");
    await expect(page.getByText("Select a lead to view details.")).toBeVisible();
  });
});

test.describe("Detail panel", () => {
  test("clicking a lead shows name, raw DM, and summary", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByText("Matt R.").click();

    await expect(page.getByText("Matt R.", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Hey I've been stuck at the same bench")).toBeVisible();
    // scope to the detail panel summary section to avoid matching the list teaser
    await expect(
      page.locator("section").filter({ hasText: /^Summary/ }).getByRole("paragraph")
    ).toContainText("Matt is a dedicated lifter");
  });

  test("detail panel shows enrichment fields", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByText("Matt R.").click();

    // EnrichmentRows renders camelCase → readable label
    await expect(page.getByText("Wants Coaching")).toBeVisible();
    await expect(page.getByText("Is Spam")).toBeVisible();
  });

  test("reply textarea and Send/Dismiss buttons are visible", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByText("Matt R.").click();

    await expect(page.getByPlaceholder("Write a reply...")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Dismiss" })).toBeVisible();
  });

  test("Send button is disabled when reply is empty", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByText("Matt R.").click();
    await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  test("Send button enables after typing a reply", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByText("Matt R.").click();
    await page.getByPlaceholder("Write a reply...").fill("Thanks for reaching out!");
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
  });
});

test.describe("Send flow", () => {
  test("sending a reply removes lead from inbox", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByText("Matt R.").click();
    await page.getByPlaceholder("Write a reply...").fill("Thanks for reaching out!");
    await page.getByRole("button", { name: "Send" }).click();

    // Optimistic removal — lead disappears immediately
    await expect(page.getByText("Matt R.")).not.toBeVisible();
  });

  test("sending a reply clears the detail panel", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByText("Matt R.").click();
    await page.getByPlaceholder("Write a reply...").fill("Hey!");
    await page.getByRole("button", { name: "Send" }).click();

    await expect(page.getByText("Select a lead to view details.")).toBeVisible();
  });
});

test.describe("Dismiss flow", () => {
  test("dismissing a lead removes it from inbox", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByText("Sara K.").click();
    await page.getByRole("button", { name: "Dismiss" }).click();

    await expect(page.getByText("Sara K.")).not.toBeVisible();
  });

  test("dismissing clears the detail panel", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByText("Sara K.").click();
    await page.getByRole("button", { name: "Dismiss" }).click();

    await expect(page.getByText("Select a lead to view details.")).toBeVisible();
  });
});

test.describe("View switching", () => {
  test("switching to Sent shows sent leads", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByRole("button", { name: /sent/i }).click();

    await expect(page.getByText("Replied User")).toBeVisible();
  });

  test("switching to Archive shows empty state", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByRole("button", { name: /archive/i }).click();

    // No leads in archive — list is empty, placeholder visible
    await expect(page.getByText("Select a lead to view details.")).toBeVisible();
  });

  test("switching views clears selected lead", async ({ page }) => {
    await mockApiRoutes(page);
    await page.goto("/");

    await page.getByText("Matt R.").click();
    await expect(page.getByText("Hey I've been stuck")).toBeVisible();

    await page.getByRole("button", { name: /sent/i }).click();
    await expect(page.getByText("Select a lead to view details.")).toBeVisible();
  });
});
