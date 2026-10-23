// Shared helpers for every page. Plain JavaScript, no build step.

const TOKEN_KEY = "finguard_token";

const session = {
  get token() { return sessionStorage.getItem(TOKEN_KEY); },
  set(token) { sessionStorage.setItem(TOKEN_KEY, token); },
  clear() { sessionStorage.removeItem(TOKEN_KEY); },
};

class ApiError extends Error {
  constructor(status, body) {
    super(body && body.detail ? body.detail : `HTTP ${status}`);
    this.status = status;
    this.code = body && body.code;
    this.errors = (body && body.errors) || [];
  }
}

// Call the API; throws ApiError for any non-2xx answer.
async function api(path, { method = "GET", body, headers = {} } = {}) {
  const opts = { method, headers: { ...headers } };
  if (session.token) opts.headers.Authorization = `Bearer ${session.token}`;
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const response = await fetch(path, opts);
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (response.status === 401 && path !== "/api/auth/login") {
    session.clear();
    location.replace("/login.html?expired=1");
  }
  if (!response.ok) throw new ApiError(response.status, data);
  return data;
}

// Turn an ApiError into one human-readable sentence.
function errorMessage(err) {
  const messages = {
    INSUFFICIENT_FUNDS: "Insufficient funds on the selected account.",
    CURRENCY_MISMATCH: "Both accounts must have the same currency.",
    IDEMPOTENCY_KEY_REUSED: "This transfer was already submitted with different details.",
  };
  if (messages[err.code]) return messages[err.code];
  if (err.code === "VALIDATION_ERROR" && err.errors.length) {
    const first = err.errors[0];
    const field = first.loc[first.loc.length - 1];
    return `${field}: ${first.msg}`;
  }
  return err.message || "Something went wrong. Please try again.";
}

function formatMoney(amount, currency) {
  return `${amount} ${currency}`;
}

function show(el, text) {
  el.textContent = text;
  el.hidden = false;
}

function hide(el) {
  el.hidden = true;
  el.textContent = "";
}

// Protected pages call this first: no token -> back to the login page.
async function requireAuth() {
  if (!session.token) {
    location.replace("/login.html");
    return new Promise(() => {}); // never resolves: the page is being left
  }
  const user = await api("/api/users/me");
  document.querySelector("[data-testid=current-user]").textContent = user.full_name;
  document.querySelector("[data-testid=logout-button]").addEventListener("click", () => {
    session.clear();
    location.replace("/login.html?logged_out=1");
  });
  return user;
}

async function loadAccounts() {
  return api("/api/accounts");
}

function renderAccountRows(tbody, accounts) {
  tbody.innerHTML = "";
  for (const a of accounts) {
    const row = document.createElement("tr");
    row.dataset.testid = `account-row-${a.id}`;
    for (const [text, testid] of [[`#${a.id}`], [a.currency], [formatMoney(a.balance, a.currency), "balance"]]) {
      const td = document.createElement("td");
      td.textContent = text;
      if (testid) {
        td.dataset.testid = testid;
        td.className = "money";
      }
      row.appendChild(td);
    }
    tbody.appendChild(row);
  }
}

function fillAccountSelect(select, accounts) {
  select.innerHTML = "";
  for (const a of accounts) {
    const option = document.createElement("option");
    option.value = a.id;
    option.textContent = `#${a.id} — ${formatMoney(a.balance, a.currency)}`;
    select.appendChild(option);
  }
}
