const form = document.getElementById("signup-form");
const messageBox = document.getElementById("message");

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    const password = document.getElementById("password").value;
    const confirmPassword = document.getElementById("confirm_password").value;

    if (password !== confirmPassword) {
        showMessage("Password and Confirm Password do not match.", "error");
        return;
    }

    const payload = {
        first_name: document.getElementById("first_name").value.trim(),
        last_name: document.getElementById("last_name").value.trim(),
        login_id: document.getElementById("login_id").value.trim(),
        password: password,
        confirm_password: confirmPassword,
    };

    try {
        const response = await fetch("/auth/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();

        if (!response.ok) {
            const detail = Array.isArray(data.detail)
                ? data.detail.map((d) => d.msg).join(", ")
                : data.detail;
            showMessage(detail || "Signup failed", "error");
            return;
        }

        showMessage("Customer registration successful. login to continue", "success");
        form.reset();
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
});
