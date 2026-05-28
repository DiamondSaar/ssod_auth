// Общий JS-файл SSOD Auth Center.
// Пока здесь нет бизнес-логики. Файл оставлен как точка расширения проекта.


function previewAvatar(input) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.getElementById("avatar-preview");
            if (preview.tagName === "IMG") {
                preview.src = e.target.result;
            } else {
                const img = document.createElement("img");
                img.src = e.target.result;
                img.className = "uc-avatar-img";
                img.id = "avatar-preview";
                preview.replaceWith(img);
            }
        };
        reader.readAsDataURL(input.files[0]);
    }
}

