let currentThreadId = localStorage.getItem("travel_thread_id") || null;
let latestAnswerMarkdown = "";

function getAuthToken() {
    return localStorage.getItem("access_token") || "";
}

function updateAuthUI() {
    const token = getAuthToken();
    document.getElementById("authLoggedOut")?.classList.toggle("hidden", !!token);
    document.getElementById("authLoggedIn")?.classList.toggle("hidden", !token);
    if (token) document.getElementById("authUserEmail").textContent = "Signed in";
}

async function authLogin() {
    return authRequest("/auth/login");
}

async function authRegister() {
    return authRequest("/auth/register");
}

async function authRequest(path) {
    hideError();
    const email = document.getElementById("authEmail").value.trim();
    const password = document.getElementById("authPassword").value;
    let res, data;
    try {
        res = await fetch(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        });
        data = await res.json().catch(() => ({}));
    } catch (error) {
        showError("Cannot reach server. Is uvicorn running on port 8000? (" + error.message + ")");
        return;
    }
    if (!res.ok) {
        const detail = Array.isArray(data.detail) ? (data.detail[0]?.msg || "Auth failed") : (data.detail || data.error || "Auth failed");
        showError(detail);
        return;
    }
    localStorage.setItem("access_token", data.access_token);
    updateAuthUI();
    showError("");
    hideError();
}

function authLogout() {
    localStorage.removeItem("access_token");
    updateAuthUI();
}

updateAuthUI();

function setPrompt(text) {
    document.getElementById("userInput").value = text;
}

function setLoading(isLoading) {
    const sendBtn = document.getElementById("sendBtn");
    const btnText = document.getElementById("btnText");
    const btnLoader = document.getElementById("btnLoader");

    sendBtn.disabled = isLoading;

    if (isLoading) {
        btnText.classList.add("hidden");
        btnLoader.classList.remove("hidden");
    } else {
        btnText.classList.remove("hidden");
        btnLoader.classList.add("hidden");
    }
}

function showError(message) {
    const errorBox = document.getElementById("errorBox");

    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
    if (message) errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
}

function hideError() {
    const errorBox = document.getElementById("errorBox");

    errorBox.classList.add("hidden");
    errorBox.textContent = "";
}

function showResult(answer, threadId, guardBlocked) {
    latestAnswerMarkdown = answer;

    const resultSection = document.getElementById("resultSection");
    const resultBox = document.getElementById("resultBox");
    const threadInfo = document.getElementById("threadInfo");
    const resultActions = document.querySelector(".result-actions");

    if (resultActions) {
        resultActions.classList.toggle("hidden", !!guardBlocked);
    }

    if (typeof marked !== "undefined") {
        resultBox.innerHTML = marked.parse(answer);
    } else {
        resultBox.innerText = answer;
    }

    threadInfo.textContent = `Thread ID: ${threadId}`;

    resultSection.classList.remove("hidden");

    resultSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

async function sendMessage() {
    hideError();

    const input = document.getElementById("userInput");
    const message = input.value.trim();

    if (!message) {
        showError("Please enter your travel request first.");
        return;
    }

    setLoading(true);

    try {
        const headers = { "Content-Type": "application/json" };
        if (getAuthToken()) headers["Authorization"] = `Bearer ${getAuthToken()}`;
        const response = await fetch("/api/travel", {
            method: "POST",
            headers,
            body: JSON.stringify({
                message: message,
                thread_id: currentThreadId
            })
        });

        const data = await response.json().catch(() => ({}));

        if (response.status === 401) {
            localStorage.removeItem("access_token");
            updateAuthUI();
            throw new Error((data.detail || "Session expired. Please log in again.") + " (Guardrails never ran \u2014 auth blocks the request first.)");
        }

        if (!response.ok || !data.success) {
            throw new Error(data.error || data.detail || "Something went wrong.");
        }

        currentThreadId = data.thread_id;
        localStorage.setItem("travel_thread_id", currentThreadId);

        showResult(data.answer, data.thread_id, data.guard_blocked);

    } catch (error) {
        showError(error.message);
    } finally {
        setLoading(false);
    }
}

function copyResult() {
    const resultBox = document.getElementById("resultBox");
    const text = resultBox.innerText;

    if (!text) {
        return;
    }

    navigator.clipboard.writeText(text)
        .then(() => {
            const copyBtn = document.querySelector(".copy-btn");
            const oldText = copyBtn.textContent;

            copyBtn.textContent = "Copied!";

            setTimeout(() => {
                copyBtn.textContent = oldText;
            }, 1400);
        })
        .catch(() => {
            showError("Could not copy result.");
        });
}

function downloadPDF() {
    const pdfContent = document.getElementById("pdfContent");

    if (!latestAnswerMarkdown || !pdfContent) {
        showError("No travel plan available to download.");
        return;
    }
    if (typeof html2pdf === "undefined") {
        showError("PDF library failed to load. Check internet connection and retry.");
        return;
    }

    const downloadBtn = document.querySelector(".download-btn");
    const oldText = downloadBtn.textContent;

    downloadBtn.textContent = "Preparing PDF...";
    downloadBtn.disabled = true;

    const options = {
        margin: 0.5,
        filename: "ai-travel-plan.pdf",
        image: {
            type: "jpeg",
            quality: 0.98
        },
        html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: "#ffffff"
        },
        jsPDF: {
            unit: "in",
            format: "a4",
            orientation: "portrait"
        },
        pagebreak: {
            mode: ["avoid-all", "css", "legacy"]
        }
    };

    html2pdf()
        .set(options)
        .from(pdfContent)
        .save()
        .then(() => {
            downloadBtn.textContent = oldText;
            downloadBtn.disabled = false;
        })
        .catch(() => {
            downloadBtn.textContent = oldText;
            downloadBtn.disabled = false;
            showError("Could not download PDF.");
        });
}

document.addEventListener("keydown", function(event) {
    if (event.ctrlKey && event.key === "Enter") {
        sendMessage();
    }
});