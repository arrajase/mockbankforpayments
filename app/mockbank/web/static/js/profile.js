document.getElementById("create-account-btn").addEventListener("click", () => {
    window.location.href = "/create-account";
});

document.getElementById("create-upi-btn").addEventListener("click", () => {
    window.location.href = "/create-upi";
});

async function checkUpiStatus() {
    try {
        const response = await fetch(`/upi?customer_id=${encodeURIComponent(customer.customer_id)}`);
        if (response.status === 404) {
            document.getElementById("create-upi-btn").hidden = false;
        }
    } catch (err) {
        // leave button hidden if unreachable
    }
}

function formatBalance(cents, currency) {
    return `${currency} ${(cents / 100).toFixed(2)}`;
}

function renderAccounts(containerId, accounts) {
    const container = document.getElementById(containerId);
    container.innerHTML = "";

    if (accounts.length === 0) {
        const empty = document.createElement("p");
        empty.className = "empty-state";
        empty.textContent = "Create accounts to get it listed here.";
        container.appendChild(empty);
        return;
    }

    accounts.forEach((account) => {
        const tile = document.createElement("div");
        tile.className = "account-tile";
        tile.innerHTML = `
            <div class="tile-number">${account.account_number}</div>
            <div class="tile-balance">${formatBalance(account.balance_cents, account.currency)}</div>
        `;
        tile.addEventListener("click", () => {
            window.location.href = `/account?id=${encodeURIComponent(account.account_id)}`;
        });
        container.appendChild(tile);
    });
}

async function loadAccounts() {
    try {
        const response = await fetch(`/accounts?customer_id=${encodeURIComponent(customer.customer_id)}`);
        const accounts = await response.json();

        if (!response.ok) {
            renderAccounts("checking-list", []);
            renderAccounts("savings-list", []);
            return;
        }

        renderAccounts("checking-list", accounts.filter((a) => a.account_type === "checking"));
        renderAccounts("savings-list", accounts.filter((a) => a.account_type === "savings"));
    } catch (err) {
        renderAccounts("checking-list", []);
        renderAccounts("savings-list", []);
    }
}

if (customer) {
    loadAccounts();
    checkUpiStatus();
}
