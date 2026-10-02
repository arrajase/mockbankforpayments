const messageBox = document.getElementById("message");
const form = document.getElementById("edit-upi-form");
const accountSelect = document.getElementById("account_id");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

let currentUpiId = null;

async function init() {
    let upi = null;
    try {
        const upiResponse = await fetch(`/upi?customer_id=${encodeURIComponent(customer.customer_id)}`);
        if (upiResponse.status === 404) {
            window.location.href = "/create-upi";
            return;
        }
        if (!upiResponse.ok) {
            showMessage("Unable to load UPI ID.", "error");
            return;
        }
        upi = await upiResponse.json();
        currentUpiId = upi.upi_id;
        document.getElementById("upi-id-label").textContent = upi.upi_id;
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
        return;
    }

    try {
        const response = await fetch(`/accounts?customer_id=${encodeURIComponent(customer.customer_id)}`);
        const accounts = await response.json();

        if (!response.ok) {
            showMessage("Could not load your accounts.", "error");
            return;
        }

        accountSelect.innerHTML = accounts
            .map(
                (a) =>
                    `<option value="${a.account_id}" ${a.account_id === upi.account_id ? "selected" : ""}>${a.account_name} (${a.account_number})</option>`
            )
            .join("");
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    try {
        const response = await fetch(`/upi/${encodeURIComponent(currentUpiId)}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ account_id: accountSelect.value }),
        });
        const data = await response.json();

        if (!response.ok) {
            const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join(", ") : data.detail;
            showMessage(detail || "Could not update linked account", "error");
            return;
        }

        showMessage("Linked account updated successfully", "success");
        setTimeout(() => {
            window.location.href = "/profile";
        }, 1200);
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
});

if (customer) {
    init();
}
