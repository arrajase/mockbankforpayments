const accountId = new URLSearchParams(window.location.search).get("id");

document.getElementById("post-transaction-link").href = accountId ? `/post-transaction?id=${encodeURIComponent(accountId)}` : "#";
document.getElementById("account-statement-link").href = accountId ? `/account-statement?id=${encodeURIComponent(accountId)}` : "#";
document.getElementById("back-to-account-link").href = accountId ? `/account?id=${encodeURIComponent(accountId)}` : "/profile";

function showMessage(text, type) {
    const box = document.getElementById("message");
    box.textContent = text;
    box.className = `message ${type}`;
}

function formatBalance(cents, currency) {
    return `${currency} ${(cents / 100).toFixed(2)}`;
}

async function loadAccountContext() {
    try {
        const response = await fetch(`/accounts/${encodeURIComponent(accountId)}`);
        const data = await response.json();

        if (!response.ok) {
            showMessage(data.detail || "Account not found.", "error");
            return;
        }

        document.getElementById("account-context").textContent =
            `${data.account_name} (${data.account_number}) · Current Balance: ${formatBalance(data.balance_cents, data.currency)}`;
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

function renderStatement(transactions) {
    const tbody = document.getElementById("statement-rows");

    if (transactions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No transactions yet.</td></tr>`;
        return;
    }

    tbody.innerHTML = transactions
        .map(
            (t) => `
            <tr>
                <td>${t.tran_date}</td>
                <td>${t.tran_type}</td>
                <td>${t.posting_type}</td>
                <td class="amount-col">${(t.amount / 100).toFixed(2)}</td>
            </tr>
        `
        )
        .join("");
}

async function loadStatement() {
    if (!accountId) {
        showMessage("No account specified.", "error");
        return;
    }

    try {
        const response = await fetch(`/transactions?account_id=${encodeURIComponent(accountId)}`);
        const data = await response.json();

        if (!response.ok) {
            showMessage(data.detail || "Could not load statement.", "error");
            return;
        }

        renderStatement(data);
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

if (customer) {
    loadAccountContext();
    loadStatement();
}
