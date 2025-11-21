// frontend/script.js
window.onload = function () {

    // ------------------ CAROUSEL ------------------
    if (document.querySelector('.carousel-container')) {
        let slideIndex = 0;
        const slides = document.querySelectorAll(".carousel-slide");
        const prevButton = document.querySelector(".prev");
        const nextButton = document.querySelector(".next");

        function showSlides() {
            slides.forEach(s => s.style.display = "none");
            slideIndex = (slideIndex + slides.length) % slides.length;
            slides[slideIndex].style.display = "block";
        }

        prevButton && (prevButton.onclick = () => { slideIndex--; showSlides(); });
        nextButton && (nextButton.onclick = () => { slideIndex++; showSlides(); });
        showSlides();
        setInterval(() => { slideIndex++; showSlides(); }, 4000);
    }
    
    // ------------------ MODEL PREDICTION ------------------
    if (document.querySelector('.dashboard-container')) {

        const imageUploadInput = document.getElementById('image-upload-input');
        const imagePreview = document.getElementById('image-preview');
        const detectButton = document.getElementById('detect-button');
        const resultsContent = document.getElementById('results-content');

        imageUploadInput.addEventListener('change', (event) => {
            if (event.target.files[0]) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    imagePreview.src = e.target.result;
                    imagePreview.style.display = "block";
                    detectButton.disabled = false;
                };
                reader.readAsDataURL(event.target.files[0]);
            }
        });

        imagePreview.addEventListener("click", function () {
            if (imagePreview.src && imagePreview.style.display !== "none") {
                imagePreview.classList.toggle("zoomed");
            }
        });

        // Save to history in localStorage (24-hour limit)
        function saveToHistory(resultData) {
            let history = JSON.parse(localStorage.getItem("testHistory")) || [];

            const now = Date.now();
            const oneDay = 24 * 60 * 60 * 1000;

            // Remove entries older than 24 hours
            history = history.filter(item => now - item.timestamp <= oneDay);

            // Add new entry
            history.push({
                timestamp: now,
                date: new Date().toLocaleString(),
                disease: resultData.disease,
                severity: resultData.severity,
                mask: resultData.mask,
                overlay: resultData.overlay,
                image: resultData.image
            });

            localStorage.setItem("testHistory", JSON.stringify(history));
        }

        detectButton.addEventListener('click', async () => {

            resultsContent.innerHTML = `<p class="placeholder-text">🔍 Analyzing... please wait.</p>`;

            const file = imageUploadInput.files[0];
            if (!file) {
                alert("Please upload an image first!");
                return;
            }

            const formData = new FormData();
            formData.append("image", file);

            try {
                const response = await fetch("/api/predict", {
                    method: "POST",
                    body: formData
                });

                const data = await response.json();

                if (data.error) {
                    resultsContent.innerHTML = `<p class="error">❌ ${data.error}</p>`;
                    return;
                }

                const ts = Date.now();

                resultsContent.innerHTML = `
                    <div class="result-card">
                        <p class="result-title">Disease:</p>
                        <p class="result-value">${data.predicted_class ?? "Unknown"}</p>
                    </div>

                    <div class="result-card">
                        <p class="result-title">Severity:</p>
                        <p class="result-value">${data.severity_label} (${data.severity_percent}%)</p>
                    </div>

                    <div class="result-card">
                        <p class="result-title">Mask:</p>
                        <img class="result-image" src="${data.mask_url}?t=${ts}" alt="mask" />
                    </div>

                    <div class="result-card">
                        <p class="result-title">Overlay:</p>
                        <img class="result-image" src="${data.overlay_url}?t=${ts}" alt="overlay" />
                    </div>
                `;

                saveToHistory({
                    disease: data.predicted_class ?? "Unknown",
                    severity: `${data.severity_label} (${data.severity_percent}%)`,
                    mask: `${data.mask_url}?t=${ts}`,
                    overlay: `${data.overlay_url}?t=${ts}`,
                    image: imagePreview.src
                });

            } catch (err) {
                console.error(err);
                resultsContent.innerHTML = `<p class="error">❌ Server error! Check console.</p>`;
            }
        });
    }

    // ------------------ CHECK HISTORY PAGE ------------------
    if (document.getElementById("history-container")) {
        const historyContainer = document.getElementById("history-container");
        let history = JSON.parse(localStorage.getItem("testHistory")) || [];

        const now = Date.now();
        const oneDay = 24 * 60 * 60 * 1000;

        // Filter history to last 24 hours
        history = history.filter(item => now - item.timestamp <= oneDay);

        if (history.length === 0) {
            historyContainer.innerHTML = "<p>No previous tests in last 24 hours.</p>";
        } else {
            historyContainer.innerHTML = "";
            history.reverse().forEach(item => {
                historyContainer.innerHTML += `
                    <div class="history-card" style="border:1px solid #ccc; padding:15px; border-radius:10px; margin-bottom:20px;">
                        <h3>${item.disease} <span style="font-size:14px; color:#666;">(${item.date})</span></h3>
                        <p><strong>Severity:</strong> ${item.severity}</p>
                        <p><strong>Mask:</strong></p>
                        <img src="${item.mask}" style="width:150px; height:150px; object-fit:cover; border-radius:10px;">
                        <p><strong>Overlay:</strong></p>
                        <img src="${item.overlay}" style="width:150px; height:150px; object-fit:cover; border-radius:10px;">
                        <p><strong>Original Image:</strong></p>
                        <img src="${item.image}" style="width:150px; height:150px; object-fit:cover; border-radius:10px;">
                    </div>
                `;
            });
        }

        // Save the filtered history back to localStorage
        localStorage.setItem("testHistory", JSON.stringify(history));
    }

};
