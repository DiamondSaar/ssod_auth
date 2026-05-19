function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(";").shift();
    }
    return "";
}

function base64UrlToBuffer(base64url) {
    const padding = "=".repeat((4 - base64url.length % 4) % 4);
    const base64 = (base64url + padding)
        .replace(/-/g, "+")
        .replace(/_/g, "/");

    const raw = window.atob(base64);
    const buffer = new ArrayBuffer(raw.length);
    const bytes = new Uint8Array(buffer);

    for (let i = 0; i < raw.length; i += 1) {
        bytes[i] = raw.charCodeAt(i);
    }

    return buffer;
}

function bufferToBase64Url(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";

    for (let i = 0; i < bytes.byteLength; i += 1) {
        binary += String.fromCharCode(bytes[i]);
    }

    return window.btoa(binary)
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=/g, "");
}

function prepareAuthenticationOptions(options) {
    options.challenge = base64UrlToBuffer(options.challenge);

    if (options.allowCredentials) {
        options.allowCredentials = options.allowCredentials.map((credential) => ({
            ...credential,
            id: base64UrlToBuffer(credential.id),
        }));
    }

    return options;
}

function serializeAssertion(credential) {
    return {
        id: credential.id,
        rawId: bufferToBase64Url(credential.rawId),
        type: credential.type,
        response: {
            clientDataJSON: bufferToBase64Url(credential.response.clientDataJSON),
            authenticatorData: bufferToBase64Url(credential.response.authenticatorData),
            signature: bufferToBase64Url(credential.response.signature),
            userHandle: credential.response.userHandle
                ? bufferToBase64Url(credential.response.userHandle)
                : null,
        },
        clientExtensionResults: credential.getClientExtensionResults(),
    };
}

async function loginWithPasskey() {
    const statusBox = document.getElementById("passkey-login-status");
    const button = document.getElementById("passkey-login-button");

    if (!window.PublicKeyCredential) {
        statusBox.textContent = "Ваш браузер не поддерживает Passkey/WebAuthn.";
        return;
    }

    button.disabled = true;
    statusBox.textContent = "Запрашиваем параметры входа...";

    try {
        const beginResponse = await fetch("/webauthn/authentication/begin/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCookie("csrftoken"),
            },
        });

        if (!beginResponse.ok) {
            throw new Error("Не удалось начать вход через passkey.");
        }

        const options = await beginResponse.json();

        statusBox.textContent = "Подтвердите вход в браузере или операционной системе.";

        const credential = await navigator.credentials.get({
            publicKey: prepareAuthenticationOptions(options),
        });

        const completeResponse = await fetch("/webauthn/authentication/complete/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify(serializeAssertion(credential)),
        });

        if (!completeResponse.ok) {
            const text = await completeResponse.text();
            throw new Error(`Не удалось завершить вход: ${text}`);
        }

        const result = await completeResponse.json();

        window.location.href = result.redirect_url || "/account/";

    } catch (error) {
        console.error(error);
        statusBox.textContent = error.message || "Ошибка входа через passkey.";
    } finally {
        button.disabled = false;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("passkey-login-button");

    if (button) {
        button.addEventListener("click", loginWithPasskey);
    }
});
