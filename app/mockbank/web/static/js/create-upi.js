const messageBox = document.getElementById("message");
const form = document.getElementById("create-upi-form");
const accountSelect = document.getElementById("account_id");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

async function init() {
    try {
        const { ok, data: accounts } = await api("/accounts");
        if (!ok || accounts.length === 0) {
            showMessage("You need at least one account before creating a UPI ID.", "error");
            form.querySelector("button[type=submit]").disabled = true;
            return;
        }

        accountSelect.innerHTML = accounts
            .map((a) => `<option value="${escapeHtml(a.account_id)}">${escapeHtml(a.account_name)} (${escapeHtml(a.account_number)}, ${escapeHtml(a.currency)})</option>`)
            .join("");
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    const pin = document.getElementById("upi_pin").value;
    if (pin !== document.getElementById("confirm_upi_pin").value) {
        showMessage("UPI PIN and Confirm UPI PIN do not match.", "error");
        return;
    }

    const payload = {
        handle: document.getElementById("handle").value.trim(),
        account_id: accountSelect.value,
        upi_pin: pin,
    };

    try {
        const { ok, data } = await api("/upi", { method: "POST", body: payload });
        if (!ok) {
            showMessage(errorMessage(data, "Could not create UPI ID"), "error");
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
