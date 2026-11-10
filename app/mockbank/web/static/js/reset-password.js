const messageBox = document.getElementById("message");
const form = document.getElementById("reset-password-form");
const loginIdInput = document.getElementById("login_id");

// Signed out, this page is Forgot Password: ask for the login ID and hide the signed-in chrome.
const forgotMode = !customer;
if (forgotMode) {
    document.body.classList.add("signed-out");
    document.title = "MockBank | Forgot Password";
    document.querySelector(".main-content h1").textContent = "Forgot Password";
    document.getElementById("reset-subtitle").textContent = "Enter your Login ID and choose a new password.";
    document.getElementById("login-id-field").hidden = false;
    loginIdInput.required = true;
    const back = document.getElementById("back-link");
    back.href = "/";
    back.textContent = "Back to Login";
}

function showMessage(text, type) {
    messageBox.textContent = text;
    messageBox.className = `message ${type}`;
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.className = "message";

    const newPassword = document.getElementById("new_password").value;
    const confirmPassword = document.getElementById("confirm_password").value;
    if (newPassword !== confirmPassword) {
        showMessage("New Password and Confirm New Password do not match.", "error");
        return;
    }

    try {
        const body = { new_password: newPassword, confirm_password: confirmPassword };
        const { ok, data } = forgotMode
            ? await api("/auth/forgot-password", { method: "POST", body: { login_id: loginIdInput.value.trim(), ...body } })
            : await api("/me/password", { method: "PUT", body });
        if (!ok) {
            showMessage(errorMessage(data, "Could not reset password"), "error");
            return;
        }
        form.reset();
        showMessage(forgotMode ? "Password reset successfully. Login with your new password." : "Password reset successfully", "success");
    } catch (err) {
        showMessage("Unable to reach the server. Please try again.", "error");
    }
});
