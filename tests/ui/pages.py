"""Page Objects: one class per screen.

A Page Object knows *how* to find elements and perform actions on a page; the test
only says *what* the user does and *what* must be visible. When a locator changes,
it is fixed in one place here, not in every test.

Locators use data-testid attributes: they do not break when texts, styles or the
layout change. Playwright's expect() waits automatically, so no sleep() is needed.
"""

from playwright.sync_api import Locator, Page


class BasePage:
    path = "/"

    def __init__(self, page: Page):
        self.page = page

    def open(self):
        self.page.goto(self.path)
        return self

    def by_testid(self, testid: str) -> Locator:
        return self.page.get_by_test_id(testid)

    # The header is shared by all protected pages.
    @property
    def current_user(self) -> Locator:
        return self.by_testid("current-user")

    def logout(self) -> None:
        self.by_testid("logout-button").click()


class LoginPage(BasePage):
    path = "/login.html"

    @property
    def error(self) -> Locator:
        return self.by_testid("login-error")

    @property
    def info(self) -> Locator:
        return self.by_testid("login-info")

    def login(self, email: str, password: str) -> None:
        self.by_testid("email-input").fill(email)
        self.by_testid("password-input").fill(password)
        self.by_testid("login-button").click()


class DashboardPage(BasePage):
    path = "/dashboard.html"

    @property
    def welcome(self) -> Locator:
        return self.by_testid("welcome")

    def balance_of(self, account_id: int) -> Locator:
        return self.by_testid(f"account-row-{account_id}").get_by_test_id("balance")


class AccountsPage(BasePage):
    path = "/accounts.html"

    @property
    def success(self) -> Locator:
        return self.by_testid("accounts-success")

    @property
    def rows(self) -> Locator:
        return self.page.locator("[data-testid^=account-row-]")

    def balance_of(self, account_id: int) -> Locator:
        return self.by_testid(f"account-row-{account_id}").get_by_test_id("balance")

    def open_account(self, currency: str) -> None:
        self.by_testid("currency-select").select_option(currency)
        self.by_testid("open-account-button").click()

    def top_up(self, account_id: int, amount: str) -> None:
        self.by_testid("deposit-account-select").select_option(str(account_id))
        self.by_testid("deposit-amount-input").fill(amount)
        self.by_testid("deposit-button").click()


class TransferPage(BasePage):
    path = "/transfer.html"

    @property
    def success(self) -> Locator:
        return self.by_testid("transfer-success")

    @property
    def error(self) -> Locator:
        return self.by_testid("transfer-error")

    @property
    def submit_button(self) -> Locator:
        return self.by_testid("transfer-button")

    def fill(self, from_id: int, to_id: int | str, amount: str, description: str = "") -> None:
        # Options are loaded asynchronously; select_option waits until the option exists.
        self.by_testid("from-account-select").select_option(str(from_id))
        self.by_testid("to-account-input").fill(str(to_id))
        self.by_testid("amount-input").fill(amount)
        self.by_testid("description-input").fill(description)

    def send(self, from_id: int, to_id: int | str, amount: str, description: str = "") -> None:
        self.fill(from_id, to_id, amount, description)
        self.submit_button.click()


class HistoryPage(BasePage):
    path = "/history.html"

    def open_for(self, account_id: int):
        self.page.goto(f"{self.path}?account={account_id}")
        return self

    @property
    def rows(self) -> Locator:
        return self.by_testid("history-row")
