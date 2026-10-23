"""Balances, accounts, transfers and history through the browser."""

import pytest
from playwright.sync_api import Page, expect

from tests.ui.pages import AccountsPage, DashboardPage, HistoryPage, LoginPage, TransferPage

pytestmark = pytest.mark.ui


def test_dashboard_shows_balance_of_each_account(user, account_factory, page: Page):
    kzt = account_factory(user, balance="15000.50")
    usd = account_factory(user, balance="20.00", currency="USD")

    LoginPage(page).open().login(user.email, user.password)

    dashboard = DashboardPage(page)
    expect(dashboard.balance_of(kzt["id"])).to_have_text("15000.50 KZT")
    expect(dashboard.balance_of(usd["id"])).to_have_text("20.00 USD")


def test_open_account_and_top_up(logged_in_page: Page, user):
    accounts = AccountsPage(logged_in_page).open()

    accounts.open_account("EUR")
    expect(accounts.success).to_contain_text("(EUR) opened")
    account_id = user.api.list_accounts().json()[-1]["id"]
    accounts.top_up(account_id, "99.90")

    expect(accounts.balance_of(account_id)).to_have_text("99.90 EUR")
    assert user.api.get_balance(account_id).json()["balance"] == "99.90"


@pytest.mark.smoke
def test_transfer_updates_balance_and_shows_confirmation(logged_in_page: Page, user, other_user, account_factory):
    source = account_factory(user, balance="500.00")
    target = account_factory(other_user)
    transfer = TransferPage(logged_in_page).open()

    transfer.send(source["id"], target["id"], "120.75", description="Books")

    expect(transfer.success).to_contain_text(f"120.75 sent to account #{target['id']}")
    expect(transfer.error).to_be_hidden()
    # Cross-check the result in the backend, not only on the screen.
    assert user.api.get_balance(source["id"]).json()["balance"] == "379.25"
    assert other_user.api.get_balance(target["id"]).json()["balance"] == "120.75"


@pytest.mark.parametrize(
    ("to_account", "amount", "expected_error"),
    [
        pytest.param("", "10", "Enter the destination account number.", id="missing-recipient"),
        pytest.param("TARGET", "", "Enter an amount.", id="missing-amount"),
        pytest.param("TARGET", "0", "amount: Input should be greater than or equal to 0.01", id="zero-amount"),
        pytest.param(
            "TARGET", "10.999", "amount: Decimal input should have no more than 2 decimal places", id="three-decimals"
        ),
        pytest.param("TARGET", "100.01", "Insufficient funds on the selected account.", id="insufficient-funds"),
    ],
)
def test_transfer_form_shows_validation_errors(
    logged_in_page: Page, user, other_user, account_factory, to_account, amount, expected_error
):
    source = account_factory(user, balance="100.00")
    target = account_factory(other_user)
    transfer = TransferPage(logged_in_page).open()

    transfer.send(source["id"], target["id"] if to_account == "TARGET" else to_account, amount)

    expect(transfer.error).to_have_text(expected_error)
    expect(transfer.success).to_be_hidden()
    assert user.api.get_balance(source["id"]).json()["balance"] == "100.00"


def test_double_click_on_send_creates_only_one_transfer(logged_in_page: Page, user, account_factory):
    source = account_factory(user, balance="100.00")
    target = account_factory(user)
    transfer = TransferPage(logged_in_page).open()
    transfer.fill(source["id"], target["id"], "10.00")

    transfer.submit_button.dblclick()

    expect(transfer.success).to_be_visible()
    expect(transfer.submit_button).to_be_enabled()  # the request has finished
    debits = [e for e in user.api.history(source["id"]).json() if e["direction"] == "DEBIT"]
    assert len(debits) == 1, f"Expected exactly one transfer, got {debits}"


def test_history_shows_transfer_for_sender_and_receiver(page: Page, user, other_user, account_factory):
    source = account_factory(user, balance="300.00")
    target = account_factory(other_user)
    user.api.transfer(source["id"], target["id"], "45.00", description="Concert tickets")

    LoginPage(page).open().login(user.email, user.password)
    expect(DashboardPage(page).welcome).to_be_visible()
    history = HistoryPage(page).open_for(source["id"])

    expect(history.rows).to_have_count(2)  # the transfer and the initial top-up
    newest = history.rows.first
    expect(newest.get_by_test_id("amount")).to_have_text("-45.00")
    expect(newest.get_by_test_id("description")).to_have_text("Concert tickets")
    expect(newest.get_by_test_id("counterparty")).to_have_text(f"#{target['id']}")

    # The receiver sees the same transfer as incoming money.
    history.logout()
    LoginPage(page).login(other_user.email, other_user.password)
    expect(DashboardPage(page).welcome).to_be_visible()
    HistoryPage(page).open_for(target["id"])
    expect(history.rows).to_have_count(1)
    expect(history.rows.first.get_by_test_id("amount")).to_have_text("+45.00")
