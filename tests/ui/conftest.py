"""UI test fixtures.

pytest-playwright provides `page` (a fresh browser context per test, so cookies and
sessionStorage never leak between tests) and uses our `base_url` fixture, so
page.goto("/login.html") opens the server started in tests/conftest.py.

Test data is prepared through the API (fast and reliable), and only the behaviour
under test is driven through the browser.
"""

import pytest
from playwright.sync_api import Page, expect

from tests.ui.pages import DashboardPage, LoginPage

# Make expect() fail after 10s instead of the default 5s: CI machines can be slow.
expect.set_options(timeout=10_000)


@pytest.fixture
def logged_in_page(page: Page, user) -> Page:
    """A browser page where `user` has signed in through the login form."""
    LoginPage(page).open().login(user.email, user.password)
    expect(DashboardPage(page).welcome).to_have_text(f"Welcome, {user.full_name}")
    return page
