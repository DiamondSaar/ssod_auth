// Подтверждение входа администратора через приложение Dominex
// (телефоны без сервисов Google, где браузер не работает с ключом).
// Страница заводит одноразовый запрос, открывает приложение по ссылке
// dominex://key-confirm?flow=…, а сама ждёт, пока приложение подпишет
// запрос касанием ключа. Сервер: accounts/app_key.py.

function appKeyCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    return parts.length === 2 ? parts.pop().split(";").shift() : "";
}

async function confirmViaApp(button) {
    const statusBox = document.getElementById("app-key-status");
    button.disabled = true;
    statusBox.textContent = "Открываем приложение Dominex…";

    try {
        const startResponse = await fetch(button.dataset.startUrl, {
            method: "POST",
            headers: { "X-CSRFToken": appKeyCookie("csrftoken") },
        });
        if (!startResponse.ok) {
            throw new Error("Не удалось создать запрос на подтверждение.");
        }
        const start = await startResponse.json();

        window.location.href = start.app_url;
        statusBox.textContent = "Подтвердите вход в приложении Dominex: приложите ключ к телефону.";

        const statusUrl = `${button.dataset.startUrl}${encodeURIComponent(start.flow)}/`;
        const next = button.dataset.next;
        const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/account/";

        // Ждём до трёх минут — столько живёт запрос на сервере.
        for (let attempt = 0; attempt < 90; attempt += 1) {
            await new Promise((resolve) => setTimeout(resolve, 2000));
            const response = await fetch(statusUrl, { headers: { Accept: "application/json" } });
            if (!response.ok) {
                continue;
            }
            const status = await response.json();
            if (status.confirmed) {
                statusBox.textContent = "Вход подтверждён.";
                window.location.href = safeNext;
                return;
            }
            if (status.expired) {
                break;
            }
        }
        statusBox.textContent = "Время на подтверждение вышло. Нажмите кнопку ещё раз.";
    } catch (error) {
        console.error(error);
        statusBox.textContent = error.message || "Не удалось подтвердить вход через приложение.";
    } finally {
        button.disabled = false;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("app-key-button");
    if (button) {
        button.addEventListener("click", () => confirmViaApp(button));
    }
});
