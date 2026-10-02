if (customer) {
    document.getElementById("first_name").value = customer.first_name;
    document.getElementById("last_name").value = customer.last_name;
}

const form = document.getElementById("create-account-form");
const messageBox = document.getElementById("message");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    const accountType = document.querySelector('input[name="account_type"]:checked').value;
    const payload = {
        customer_id: customer.customer_id,
        account_type: accountType,
        account_name: document.getElementById("account_name").value.trim(),
        currency: document.getElementById("currency").value,
    };

    try {
        const response = await fetch("/accounts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();

        if (!response.ok) {
            showMessage(data.detail || "Could not create account", "error");
            return;
        }

        showMessage("Account creation successful", "success");
        setTimeout(() => {
            window.location.href = "/profile";
        }, 1200);
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
});
