const accountId = new URLSearchParams(window.location.search).get("id");

document.getElementById("post-transaction-link").href = accountId ? `/post-transaction?id=${encodeURIComponent(accountId)}` : "#";
document.getElementById("account-statement-link").href = accountId ? `/account-statement?id=${encodeURIComponent(accountId)}` : "#";
document.getElementById("back-to-account-link").href = accountId ? `/account?id=${encodeURIComponent(accountId)}` : "/profile";

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
        const { ok, data } = await api(`/accounts/${encodeURIComponent(accountId)}`);
        if (!ok) {
            showMessage(errorMessage(data, "Account not found."), "error");
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

    // The bank stamps the date and time; the form only sends what and how much.
    const amount = parseFloat(document.getElementById("amount").value || "0");
    const payload = {
        account_id: accountId,
        tran_type: document.getElementById("tran_type").value,
        amount_cents: Math.round(amount * 100),
    };

    try {
        const { ok, data } = await api("/transactions", { method: "POST", body: payload });
        if (!ok) {
            showMessage(errorMessage(data, "Could not post transaction"), "error");
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
