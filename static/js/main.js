document.addEventListener("DOMContentLoaded", () => {
  // Theme toggle
  const themeToggle = document.getElementById("themeToggle");
  const root = document.documentElement;

  function applyTheme(theme) {
    root.dataset.theme = theme;
    localStorage.setItem("expenseTrackerTheme", theme);
    if (themeToggle) {
      themeToggle.textContent = theme === "dark" ? "Light mode" : "Dark mode";
    }
  }

  function initTheme() {
    const stored = localStorage.getItem("expenseTrackerTheme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = stored || (prefersDark ? "dark" : "light");
    applyTheme(theme);
  }

  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const next = root.dataset.theme === "dark" ? "light" : "dark";
      applyTheme(next);
    });
  }

  initTheme();

  function createChart(canvas, config) {
    try {
      return new Chart(canvas, config);
    } catch (err) {
      console.warn("Chart could not be rendered", err);
      return null;
    }
  }

  const dailyCanvas = document.getElementById("dailyChart");
  if (dailyCanvas && typeof dailyLabels !== "undefined" && typeof dailyExpenses !== "undefined") {
    createChart(dailyCanvas, {
      type: "line",
      data: {
        labels: dailyLabels,
        datasets: [
          {
            label: "Daily spending",
            fill: true,
            data: dailyExpenses,
            borderColor: "#ff6b6b",
            backgroundColor: "rgba(255, 107, 107, 0.2)",
            tension: 0.3,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: (value) => `₹${value}`,
            },
          },
        },
        plugins: {
          legend: { display: false },
        },
      },
    });
  }

  const monthCanvas = document.getElementById("monthlyChart");
  if (monthCanvas && typeof monthLabels !== "undefined" && typeof monthExpenses !== "undefined") {
    createChart(monthCanvas, {
      type: "bar",
      data: {
        labels: monthLabels,
        datasets: [
          {
            label: "Monthly expenses",
            data: monthExpenses,
            backgroundColor: "rgba(13, 110, 253, 0.6)",
            borderColor: "rgba(13, 110, 253, 1)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: (value) => `₹${value}`,
            },
          },
        },
        plugins: {
          legend: { display: false },
        },
      },
    });
  }

  const categoryCanvas = document.getElementById("categoryChart");
  if (categoryCanvas && typeof categoryBreakdown !== "undefined") {
    const labels = categoryBreakdown.map((row) => row._id || "Other");
    const data = categoryBreakdown.map((row) => row.total || 0);

    createChart(categoryCanvas, {
      type: "pie",
      data: {
        labels,
        datasets: [
          {
            data,
            backgroundColor: [
              "#0d6efd",
              "#dc3545",
              "#198754",
              "#ffc107",
              "#6f42c1",
              "#fd7e14",
              "#20c997",
            ],
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            position: "bottom",
          },
        },
      },
    });
  }

  // Simple notification system for budget levels
  const budgetInfo = document.getElementById("budgetInfo");
  if (budgetInfo && "Notification" in window) {
    const budgetLevel = budgetInfo.dataset.level;
    const budgetAlert = budgetInfo.dataset.alert;
    if (budgetLevel && budgetAlert) {
      if (Notification.permission === "granted") {
        new Notification("Budget alert", {
          body: budgetAlert,
          icon: "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/icons/bell-fill.svg",
        });
      } else {
        Notification.requestPermission();
      }
    }
  }

  // Show motivational quote modal after adding a transaction
  const quoteModalEl = document.getElementById("transactionQuoteModal");
  if (quoteModalEl && typeof bootstrap !== "undefined") {
    const quote = quoteModalEl.dataset.quote;
    if (quote) {
      const modal = new bootstrap.Modal(quoteModalEl);
      modal.show();
    }
  }
});
