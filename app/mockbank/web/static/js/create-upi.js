const messageBox = document.getElementById("message");
const form = document.getElementById("create-upi-form");
const accountSelect = document.getElementById("account_id");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

async function init() {
    try {
        const upiResponse = await fetch(`/upi?customer_id=${encodeURIComponent(customer.customer_id)}`);
        if (upiResponse.ok) {
            window.location.href = "/edit-upi";
            return;
        }
    } catch (err) {
        // no UPI yet, continue
    }

    try {
        const response = await fetch(`/accounts?customer_id=${encodeURIComponent(customer.customer_id)}`);
        const accounts = await response.json();

        if (!response.ok || accounts.length === 0) {
            showMessage("You need at least one account before creating a UPI ID.", "error");
            form.querySelector("button[type=submit]").disabled = true;
            return;
        }

        accountSelect.innerHTML = accounts
            .map((a) => `<option value="${a.account_id}">${a.account_name} (${a.account_number})</option>`)
            .join("");
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    const payload = {
        customer_id: customer.customer_id,
        handle: document.getElementById("handle").value.trim(),
        account_id: accountSelect.value,
    };

    try {
        const response = await fetch("/upi", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();

        if (!response.ok) {
            const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join(", ") : data.detail;
            showMessage(detail || "Could not create UPI ID", "error");
            return;
        }

        showMessage(`UPI ID ${data.upi_id} created successfully`, "success");
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
