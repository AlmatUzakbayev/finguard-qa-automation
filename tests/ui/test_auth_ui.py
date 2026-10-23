"""Sign in, sign out and access to protected pages."""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.ui.pages import DashboardPage, LoginPage

pytestmark = pytest.mark.ui


@pytest.mark.smoke
def test_login_with_valid_credentials_opens_dashboard(page: Page, user):
    login = LoginPage(page).open()

    login.login(user.email, user.password)

    dashboard = DashboardPage(page)
    expect(page).to_have_url(re.compile(r"/dashboard\.html$"))
    expect(dashboard.welcome).to_have_text(f"Welcome, {user.full_name}")
    expect(dashboard.current_user).to_have_text(user.full_name)


def test_login_with_wrong_password_shows_error(page: Page, user):
    login = LoginPage(page).open()

    login.login(user.email, "Definitely-Wrong-1")

    expect(login.error).to_have_text("Invalid email or password.")
    expect(page).to_have_url(re.compile(r"/login\.html$"))


@pytest.mark.parametrize("path", ["/dashboard.html", "/accounts.html", "/transfer.html", "/history.html"])
def test_protected_page_redirects_anonymous_user_to_login(page: Page, path):
    page.goto(path)

    expect(page).to_have_url(re.compile(r"/login\.html"))


def test_logout_ends_the_session(logged_in_page: Page):
    dashboard = DashboardPage(logged_in_page)

    dashboard.logout()

    login = LoginPage(logged_in_page)
    expect(login.info).to_have_text("You have been signed out.")
    # The session is really gone: opening a protected page again leads back to login.
    dashboard.open()
    expect(logged_in_page).to_have_url(re.compile(r"/login\.html"))
