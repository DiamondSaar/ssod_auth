function getCookie(name) {
    // Django CSRF хранится в cookie csrftoken.
    // Для POST-запросов из fetch его надо отправлять вручную.
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(";").shift();
    }
    return "";
}

function base64UrlToBuffer(base64url) {
    // WebAuthn работает с ArrayBuffer,
    // а сервер отдает challenge/id в base64url.
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
    // ArrayBuffer обратно в base64url для отправки серверу.
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

function prepareCreationOptions(options) {
    // Конвертируем поля, которые браузер ждет как ArrayBuffer.
    options.challenge = base64UrlToBuffer(options.challenge);
    options.user.id = base64UrlToBuffer(options.user.id);

    if (options.excludeCredentials) {
        options.excludeCredentials = options.excludeCredentials.map((credential) => ({
            ...credential,
            id: base64UrlToBuffer(credential.id),
        }));
    }

    return options;
}

function serializeCredential(credential) {
    // Приводим PublicKeyCredential к JSON-формату,
    // который можно отправить на сервер.
    return {
        id: credential.id,
        rawId: bufferToBase64Url(credential.rawId),
        type: credential.type,
        response: {
            clientDataJSON: bufferToBase64Url(credential.response.clientDataJSON),
            attestationObject: bufferToBase64Url(credential.response.attestationObject),
        },
        clientExtensionResults: credential.getClientExtensionResults(),
    };
}

async function registerPasskey() {
    const statusBox = document.getElementById("passkey-status");
    const button = document.getElementById("passkey-register-button");

    if (!window.PublicKeyCredential) {
        statusBox.textContent = "Ваш браузер не поддерживает Passkey/WebAuthn.";
        return;
    }

    button.disabled = true;
    statusBox.textContent = "Запрашиваем параметры регистрации...";

    try {
        const beginResponse = await fetch("/webauthn/registration/begin/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCookie("csrftoken"),
            },
        });

        if (!beginResponse.ok) {
            throw new Error("Не удалось начать регистрацию passkey.");
        }

        const options = await beginResponse.json();

        statusBox.textContent = "Подтвердите создание passkey в браузере или операционной системе.";

        const credential = await navigator.credentials.create({
            publicKey: prepareCreationOptions(options),
        });

        const completeResponse = await fetch("/webauthn/registration/complete/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify(serializeCredential(credential)),
        });

        if (!completeResponse.ok) {
            const text = await completeResponse.text();
            throw new Error(`Не удалось завершить регистрацию passkey: ${text}`);
        }

        statusBox.textContent = "Passkey успешно добавлен. Обновляем страницу...";
        window.location.reload();

    } catch (error) {
        console.error(error);
        statusBox.textContent = error.message || "Ошибка регистрации passkey.";
    } finally {
        button.disabled = false;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("passkey-register-button");

    if (button) {
        button.addEventListener("click", registerPasskey);
    }
});
