const accountId = new URLSearchParams(window.location.search).get("id");

const backLink = document.getElementById("back-to-account-link");
if (backLink) {
    backLink.href = accountId ? `/account?id=${encodeURIComponent(accountId)}` : "/profile";
}

const postTxLink = document.getElementById("post-transaction-link");
if (postTxLink && accountId) {
    postTxLink.href = `/post-transaction?id=${encodeURIComponent(accountId)}`;
}

const stmtLink = document.getElementById("account-statement-link");
if (stmtLink && accountId) {
    stmtLink.href = `/account-statement?id=${encodeURIComponent(accountId)}`;
}

const accountIdLabel = document.getElementById("account-id-label");
if (accountIdLabel) {
    accountIdLabel.textContent = accountId || "(none)";
}
