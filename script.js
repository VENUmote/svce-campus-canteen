"use strict";

const API_BASE = "/api";
const MAX_QUANTITY = 20;
const MENU_CATEGORIES = [
    { id: "tiffins", title: "Tiffins", subtitle: "A lovely start to your day.", note: "SOUTH INDIAN FAVOURITES" },
    { id: "lunch", title: "Lunch", subtitle: "Something comforting, made for your lunch break.", note: "THE LUNCH TABLE" },
    { id: "snacks", title: "Snacks", subtitle: "A little treat between lectures.", note: "LITTLE BITES, BIG SMILES" },
    { id: "cooldrinks", title: "Drinks", subtitle: "Something cool to sip and savour.", note: "SIPS & SHAKES" },
    { id: "fastfood", title: "Fast food", subtitle: "Campus classics with a fun twist.", note: "MADE FOR SHARING" }
];

let foods = [];
let cart = new Map();
let quantities = {};
let currentCategory = "all";
let toastTimer;

const money = amount => `₹${Number(amount).toLocaleString("en-IN")}`;
const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
})[character]);

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: { "Content-Type": "application/json", ...options.headers }
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The request could not be completed.");
    return result;
}

async function loadMenu() {
    const feedback = document.getElementById("menuFeedback");
    try {
        const result = await apiRequest("/menu");
        foods = result.items;
        updateMenuCounts();
        renderMenu();
        feedback.textContent = `${foods.length} freshly priced favourites`;
    } catch (error) {
        feedback.textContent = "The menu couldn't load. Please refresh to try again.";
        feedback.classList.add("error-message");
        console.error("Menu load failed:", error);
    }
}

function updateMenuCounts() {
    document.querySelectorAll("[data-category-count]").forEach(count => {
        const category = count.dataset.categoryCount;
        count.textContent = String(category === "all"
            ? foods.length
            : foods.filter(food => food.category === category).length);
    });
    document.getElementById("heroMenuCount").textContent = String(foods.length);
    document.getElementById("aboutMenuCount").textContent = String(foods.length);
}

function renderMenu() {
    const query = document.getElementById("searchInput").value.trim().toLowerCase();
    const container = document.getElementById("foodContainer");
    container.innerHTML = "";
    const visibleFoods = foods.filter(food =>
        (currentCategory === "all" || food.category === currentCategory)
        && `${food.name} ${food.categoryLabel}`.toLowerCase().includes(query)
    );

    if (!visibleFoods.length) {
        container.innerHTML = '<div class="empty-menu"><span>✳</span><h3>No bites found just yet</h3><p>Try another search or category.</p></div>';
        return;
    }

    const categories = currentCategory === "all"
        ? MENU_CATEGORIES
        : MENU_CATEGORIES.filter(category => category.id === currentCategory);

    categories.forEach(category => {
        const categoryFoods = visibleFoods.filter(food => food.category === category.id);
        if (!categoryFoods.length) return;

        const section = document.createElement("section");
        section.className = "menu-category-section";
        section.dataset.menuSection = category.id;
        section.innerHTML = `
            <div class="menu-category-heading">
                <div><p class="eyebrow">${escapeHtml(category.note)}</p>
                <h3>${escapeHtml(category.title)}<span>${String(categoryFoods.length).padStart(2, "0")}</span></h3>
                <p class="menu-category-subtitle">${escapeHtml(category.subtitle)}</p></div>
                <span class="menu-category-flourish" aria-hidden="true">✿</span>
            </div>
            <div class="food-grid"></div>`;
        const grid = section.querySelector(".food-grid");

        categoryFoods.forEach(food => {
            const card = document.createElement("article");
            card.className = "food-card";
            card.innerHTML = `
                <div class="food-photo">
                    <img src="${escapeHtml(food.image)}" alt="${escapeHtml(food.name)}" loading="lazy">
                    <span class="food-category">${escapeHtml(food.categoryLabel)}</span>
                    ${food.imageSourceUrl ? `<a class="food-credit" href="${escapeHtml(food.imageSourceUrl)}" target="_blank" rel="noopener noreferrer" aria-label="${escapeHtml(`Photo: ${food.imageTitle} by ${food.imageCreator}, ${food.imageLicense}`)}" title="${escapeHtml(`Photo: ${food.imageTitle} by ${food.imageCreator}, ${food.imageLicense}`)}">ⓘ ${escapeHtml(food.imageCreator)}</a>` : ""}
                </div>
                <div class="food-details">
                    <div class="food-title"><h3>${escapeHtml(food.name)}</h3><span class="price">${money(food.price)}</span></div>
                    <p class="food-description">${escapeHtml(food.description)}</p>
                    <div class="food-order-row">
                        <div class="quantity" aria-label="Quantity for ${escapeHtml(food.name)}">
                            <button type="button" data-quantity="${food.id}" data-change="-1" aria-label="Decrease ${escapeHtml(food.name)} quantity">−</button>
                            <span id="qty-${food.id}">1</span>
                            <button type="button" data-quantity="${food.id}" data-change="1" aria-label="Increase ${escapeHtml(food.name)} quantity">+</button>
                        </div>
                        <button type="button" class="add-btn" data-add="${food.id}">Add to bag <span>+</span></button>
                    </div>
                </div>`;
            grid.appendChild(card);
        });
        container.appendChild(section);
    });
}

function changeQuantity(id, change) {
    const nextQuantity = Math.min(MAX_QUANTITY, Math.max(1, (quantities[id] || 1) + change));
    quantities[id] = nextQuantity;
    const quantityElement = document.getElementById(`qty-${id}`);
    if (quantityElement) quantityElement.textContent = String(nextQuantity);
}

function addToCart(id) {
    const food = foods.find(item => item.id === id);
    if (!food) return;
    const existing = cart.get(id) || 0;
    const quantity = Math.min(MAX_QUANTITY, existing + (quantities[id] || 1));
    cart.set(id, quantity);
    updateCart();
    showToast(`${food.name} added to your bag`);
}

function updateCart() {
    const count = [...cart.values()].reduce((sum, quantity) => sum + quantity, 0);
    document.getElementById("cartCount").textContent = String(count);
    document.getElementById("cartHeadingCount").textContent = count ? ` · ${count}` : "";
    renderCart();
}

function renderCart() {
    const container = document.getElementById("cartItems");
    container.innerHTML = "";
    for (const [id, quantity] of cart) {
        const food = foods.find(item => item.id === id);
        if (!food) continue;
        const row = document.createElement("div");
        row.className = "cart-item";
        row.innerHTML = `
            <img src="${escapeHtml(food.image)}" alt="">
            <div class="cart-item-info"><strong>${escapeHtml(food.name)}</strong><span>${money(food.price)} each</span></div>
            <div class="cart-item-controls">
                <button type="button" data-cart-quantity="${id}" data-change="-1" aria-label="Remove one ${escapeHtml(food.name)}">−</button>
                <span>${quantity}</span>
                <button type="button" data-cart-quantity="${id}" data-change="1" aria-label="Add one ${escapeHtml(food.name)}">+</button>
            </div>
            <strong class="cart-line-total">${money(food.price * quantity)}</strong>`;
        container.appendChild(row);
    }
    if (!cart.size) {
        container.innerHTML = '<div class="empty-cart"><span>✳</span><h3>Your bag is taking a break.</h3><p>Add a favourite and it will show up here.</p><button type="button" onclick="closeCart(); document.getElementById(\'menu\').scrollIntoView({behavior:\'smooth\'})">Browse the menu</button></div>';
    }
    renderSummary();
    document.getElementById("placeOrderButton").disabled = cart.size === 0;
}

function localBill() {
    const subtotal = [...cart].reduce((sum, [id, quantity]) => {
        const food = foods.find(item => item.id === id);
        return sum + (food ? food.price * quantity : 0);
    }, 0);
    const discount = subtotal >= 250 ? Math.floor((subtotal * 5 + 50) / 100) : 0;
    return { subtotal, discount, total: subtotal - discount };
}

function renderSummary() {
    const { subtotal, discount, total } = localBill();
    document.getElementById("billSummary").innerHTML = `
        <div><span>Subtotal</span><strong>${money(subtotal)}</strong></div>
        <div class="${discount ? "saver-line" : ""}"><span>Campus Saver ${discount ? "(5%)" : "(₹250+)"}</span><strong>${discount ? `−${money(discount)}` : "—"}</strong></div>
        <div class="bill-total"><span>Total to pay</span><strong>${money(total)}</strong></div>`;
}

function openCart() {
    const overlay = document.getElementById("cartOverlay");
    overlay.classList.add("is-open");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    document.getElementById("customerName").focus();
}

function closeCart() {
    const overlay = document.getElementById("cartOverlay");
    overlay.classList.remove("is-open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
}

function showBill(bill) {
    const lines = bill.items.map(item => `
        <tr><td>${escapeHtml(item.name)}<small>${item.quantity} × ${money(item.unitPrice)}</small></td><td>${money(item.lineTotal)}</td></tr>
    `).join("");
    document.getElementById("receiptContent").innerHTML = `
        <div class="receipt-brand"><img class="logo-image" src="canteen-logo.svg" alt=""><span>SVCE canteen<small>GOOD FOOD, GOOD COMPANY</small></span></div>
        <p class="eyebrow receipt-kicker">ORDER CONFIRMED</p>
        <h2 id="receiptTitle">A little something<br>to look forward to.</h2>
        <div class="receipt-number"><span>YOUR BILL</span><strong>${escapeHtml(bill.orderNumber)}</strong></div>
        <div class="receipt-meta"><span>Placed for <strong>${escapeHtml(bill.customerName)}</strong>${bill.studentId ? `<br><small>${escapeHtml(bill.studentId)}</small>` : ""}</span><span>${escapeHtml(bill.createdAt)}<br><small>Pay by ${escapeHtml(bill.paymentMethod)} at pickup</small></span></div>
        <table class="receipt-table"><thead><tr><th>Item</th><th>Amount</th></tr></thead><tbody>${lines}</tbody></table>
        <div class="receipt-totals"><div><span>Subtotal</span><strong>${money(bill.subtotal)}</strong></div>
        <div class="${bill.discount ? "saver-line" : ""}"><span>Campus Saver ${bill.discount ? "(5%)" : ""}</span><strong>${bill.discount ? `−${money(bill.discount)}` : money(0)}</strong></div>
        <div class="receipt-grand-total"><span>Amount due</span><strong>${money(bill.total)}</strong></div></div>
        <p class="receipt-thanks">Thanks for supporting your campus canteen ✳</p>`;
    const overlay = document.getElementById("billOverlay");
    overlay.classList.add("is-open");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
}

async function placeOrder(event) {
    event.preventDefault();
    if (!cart.size) return;
    const formElement = event.currentTarget;
    const button = document.getElementById("placeOrderButton");
    const errorElement = document.getElementById("checkoutError");
    errorElement.textContent = "";
    button.disabled = true;
    button.innerHTML = "Preparing your bill…";
    const form = new FormData(event.currentTarget);
    const payload = {
        customerName: form.get("customerName"),
        studentId: form.get("studentId"),
        paymentMethod: form.get("paymentMethod"),
        items: [...cart].map(([id, quantity]) => ({ id, quantity }))
    };
    try {
        const result = await apiRequest("/orders", { method: "POST", body: JSON.stringify(payload) });
        cart.clear();
        updateCart();
        formElement.reset();
        closeCart();
        showBill(result.bill);
    } catch (error) {
        errorElement.textContent = error.message;
        console.error("Order creation failed:", error);
    } finally {
        button.disabled = cart.size === 0;
        button.innerHTML = 'Create my bill <span>↗</span>';
    }
}

function closeBill() {
    const overlay = document.getElementById("billOverlay");
    overlay.classList.remove("is-open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
}

function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2400);
}

document.getElementById("foodContainer").addEventListener("click", event => {
    const target = event.target.closest("button");
    if (!target) return;
    if (target.dataset.add) addToCart(Number(target.dataset.add));
    if (target.dataset.quantity) changeQuantity(Number(target.dataset.quantity), Number(target.dataset.change));
});

document.getElementById("cartItems").addEventListener("click", event => {
    const target = event.target.closest("[data-cart-quantity]");
    if (!target) return;
    const id = Number(target.dataset.cartQuantity);
    const next = (cart.get(id) || 0) + Number(target.dataset.change);
    if (next <= 0) cart.delete(id);
    else cart.set(id, Math.min(MAX_QUANTITY, next));
    updateCart();
});

document.addEventListener("error", event => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement)
        || !image.matches(".food-photo img, .cart-item img")
        || image.dataset.fallback) return;
    image.dataset.fallback = "true";
    image.src = "/food-placeholder.svg";
    if (!image.alt) image.alt = "Food photo temporarily unavailable";
}, true);

document.querySelector(".categories").addEventListener("click", event => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    currentCategory = button.dataset.category;
    document.querySelectorAll(".category-chip").forEach(chip => chip.classList.toggle("active", chip === button));
    renderMenu();
});

document.getElementById("searchInput").addEventListener("input", renderMenu);
document.getElementById("checkoutForm").addEventListener("submit", placeOrder);
document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
        closeCart();
        closeBill();
    }
    if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
        event.preventDefault();
        document.getElementById("searchInput").focus();
    }
});

updateCart();
loadMenu();
