const accountId = new URLSearchParams(window.location.search).get("id");

document.getElementById("post-transaction-link").href = accountId ? `/post-transaction?id=${encodeURIComponent(accountId)}` : "#";
document.getElementById("account-statement-link").href = accountId ? `/account-statement?id=${encodeURIComponent(accountId)}` : "#";
document.getElementById("back-to-account-link").href = accountId ? `/account?id=${encodeURIComponent(accountId)}` : "/profile";

const todayIso = new Date().toISOString().slice(0, 10);
document.getElementById("tran_date").value = todayIso;

const messageBox = document.getElementById("message");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

function formatBalance(cents, currency) {
    return `${currency} ${(cents / 100).toFixed(2)}`;
}

async function loadAccountContext() {
    if (!accountId) {
        showMessage("No account specified.", "error");
        return;
    }

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

const form = document.getElementById("post-transaction-form");
form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    if (!accountId) {
        showMessage("No account specified.", "error");
        return;
    }

    const dollars = parseFloat(document.getElementById("amount").value || "0");
    const payload = {
        account_id: accountId,
        tran_type: document.getElementById("tran_type").value,
        amount_cents: Math.round(dollars * 100),
        tran_date: document.getElementById("tran_date").value,
    };

    try {
        const response = await fetch("/transactions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();

        if (!response.ok) {
            const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join(", ") : data.detail;
            showMessage(detail || "Could not post transaction", "error");
            return;
        }

        showMessage("Transaction posted successfully", "success");
        setTimeout(() => {
            window.location.href = `/account?id=${encodeURIComponent(accountId)}`;
        }, 1200);
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
});

if (customer) {
    loadAccountContext();
}
