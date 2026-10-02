function showMessage(text, type) {
    const box = document.getElementById("message");
    box.textContent = text;
    box.className = `message ${type}`;
}

function formatBalance(cents, currency) {
    return `${currency} ${(cents / 100).toFixed(2)}`;
}

function renderDetails(account) {
    const container = document.getElementById("details");
    const rows = [
        ["Account Name", account.account_name],
        ["Account Number", account.account_number],
        ["Account Type", account.account_type.charAt(0).toUpperCase() + account.account_type.slice(1)],
        ["Balance", formatBalance(account.balance_cents, account.currency)],
        ["Currency", account.currency],
        ["Owner", account.owner_name],
    ];
    container.innerHTML = rows
        .map(([label, value]) => `
            <div class="detail-row">
                <span class="detail-label">${label}</span>
                <span class="detail-value">${value}</span>
            </div>
        `)
        .join("");
}

async function loadAccount() {
    const accountId = new URLSearchParams(window.location.search).get("id");
    if (!accountId) {
        showMessage("No account specified.", "error");
        return;
    }

    document.getElementById("post-transaction-link").href = `/post-transaction?id=${encodeURIComponent(accountId)}`;
    document.getElementById("account-statement-link").href = `/account-statement?id=${encodeURIComponent(accountId)}`;

    try {
        const response = await fetch(`/accounts/${encodeURIComponent(accountId)}`);
        const data = await response.json();

        if (!response.ok) {
            showMessage(data.detail || "Account not found.", "error");
            return;
        }

        renderDetails(data);
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

if (customer) {
    loadAccount();
}
