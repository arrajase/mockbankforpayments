document.getElementById("create-account-btn").addEventListener("click", () => {
    window.location.href = "/create-account";
});

document.getElementById("create-upi-btn").addEventListener("click", () => {
    window.location.href = "/create-upi";
});

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
            <div class="tile-number">${escapeHtml(account.account_number)}</div>
            <div class="tile-balance">${escapeHtml(formatBalance(account.balance_cents, account.currency))}</div>
        `;
        tile.addEventListener("click", () => {
            window.location.href = `/account?id=${encodeURIComponent(account.account_id)}`;
        });
        container.appendChild(tile);
    });
}

async function loadAccounts() {
    try {
        const { ok, data: accounts } = await api("/accounts");
        if (!ok) {
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

// ---------- Mobile number ----------

const mobileForm = document.getElementById("mobile-form");
const mobileInput = document.getElementById("mobile_number");

function showMobileMessage(text, type) {
    const box = document.getElementById("mobile-message");
    box.textContent = text;
    box.className = `message ${type}`;
}

function renderMobile(mobileNumber) {
    mobileInput.value = mobileNumber || "";
    document.getElementById("mobile-note").textContent = mobileNumber
        ? "Apps can find the UPI ID you link to this number. Changing it moves that link to the new number."
        : "Add your mobile number. You can then link it to one of your UPI IDs on the Edit UPI ID page.";
    document.getElementById("mobile-submit").textContent = mobileNumber ? "UPDATE MOBILE NUMBER" : "ADD MOBILE NUMBER";
}

async function loadMobile() {
    try {
        const { ok, data } = await api("/me");
        if (ok) renderMobile(data.mobile_number);
    } catch (err) {
        // leave the form empty if unreachable
    }
}

mobileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        const { ok, data } = await api("/me/mobile", { method: "PUT", body: { mobile_number: mobileInput.value.trim() } });
        if (!ok) {
            showMobileMessage(errorMessage(data, "Could not save mobile number"), "error");
            return;
        }
        renderMobile(data.mobile_number);
        showMobileMessage("Mobile number saved.", "success");
        loadCustomerDetails();
    } catch (err) {
        showMobileMessage("Unable to reach the server. Please try again.", "error");
    }
});

// ---------- App access toggles ----------

const PURPOSES = [
    ["LINK", "Confirm UPI ID"],
    ["BALANCE", "Balance"],
    ["STATEMENT", "Statement"],
];

function showAccessMessage(text, type) {
    const box = document.getElementById("app-access-message");
    box.textContent = text;
    box.className = `message ${type}`;
}

function renderAppAccess(rows) {
    const section = document.getElementById("app-access-section");
    const list = document.getElementById("app-access-list");
    section.hidden = rows.length === 0;

    list.innerHTML = rows
        .map(
            (row) => `
            <div class="request-card">
                <div class="request-title">${escapeHtml(row.client_name)}</div>
                <div class="request-meta">UPI ID ${escapeHtml(row.upi_id)}</div>
                <div class="toggle-row">
                    ${PURPOSES.map(([purpose, label]) => {
                        const state = row.purposes[purpose];
                        const until = state.enabled ? `until ${new Date(state.expires_at).toLocaleDateString()}` : "";
                        return `
                        <label class="toggle">
                            <input type="checkbox" data-client="${escapeHtml(row.client_id)}" data-upi="${escapeHtml(row.upi_id)}"
                                   data-purpose="${purpose}" ${state.enabled ? "checked" : ""}>
                            <span class="switch"></span>
                            <span>${escapeHtml(label)}</span>
                            <span class="until">${escapeHtml(until)}</span>
                        </label>`;
                    }).join("")}
                </div>
            </div>
        `
        )
        .join("");

    list.querySelectorAll("input[type=checkbox]").forEach((box) => {
        box.addEventListener("change", () => setAccess(box));
    });
}

async function setAccess(box) {
    const enabled = box.checked;
    const pinInput = document.getElementById("app-access-pin");
    const body = { client_id: box.dataset.client, upi_id: box.dataset.upi, purpose: box.dataset.purpose, enabled };

    if (enabled) {
        if (!pinInput.value) {
            box.checked = false;
            showAccessMessage("Enter your UPI PIN above to turn access on.", "error");
            pinInput.focus();
            return;
        }
        body.upi_pin = pinInput.value;
    }

    box.disabled = true;
    try {
        const { ok, data } = await api("/me/app-access", { method: "PUT", body });
        if (!ok) {
            box.checked = !enabled;
            showAccessMessage(errorMessage(data, "Could not change app access"), "error");
            return;
        }
        showAccessMessage(enabled ? "Access turned on." : "Access turned off.", "success");
        loadAppAccess();
    } catch (err) {
        box.checked = !enabled;
        showAccessMessage("Unable to reach the server. Please try again.", "error");
    } finally {
        box.disabled = false;
    }
}

async function loadAppAccess() {
    try {
        const { ok, data } = await api("/me/app-access");
        if (ok) renderAppAccess(data);
    } catch (err) {
        // leave the section hidden if unreachable
    }
}

if (customer) {
    loadMobile();
    loadAccounts();
    loadAppAccess();
}
