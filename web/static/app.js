/**
 * BestBuyTool Frontend Controller
 */

// Global State
let suppliersList = [];
let currentResults = [];

// DOM Elements
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const countrySelect = document.getElementById('country-select');
const suppliersGrid = document.getElementById('suppliers-list');
const selectAllBtn = document.getElementById('select-all-btn');
const deselectAllBtn = document.getElementById('deselect-all-btn');

const bestBuyBanner = document.getElementById('best-buy-banner');
const bestBuyName = document.getElementById('best-buy-name');
const bestBuyPrice = document.getElementById('best-buy-price');
const bestBuySupplier = document.getElementById('best-buy-supplier');
const bestBuyLink = document.getElementById('best-buy-link');

const resultsSection = document.getElementById('results-section');
const resultsCount = document.getElementById('results-count');
const resultsTbody = document.getElementById('results-tbody');
const exportCsvBtn = document.getElementById('export-csv-btn');

const loadingState = document.getElementById('loading-state');
const toastContainer = document.getElementById('toast-container');

// Startup Initialization
document.addEventListener('DOMContentLoaded', () => {
    loadSuppliers();
    setupEventListeners();
});

// Setup Event Listeners
function setupEventListeners() {
    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });

    countrySelect.addEventListener('change', filterSuppliersByCountry);
    selectAllBtn.addEventListener('click', () => toggleAllSuppliers(true));
    deselectAllBtn.addEventListener('click', () => toggleAllSuppliers(false));

    exportCsvBtn.addEventListener('click', exportResultsToCSV);
}

// Fetch configured suppliers from API
async function loadSuppliers() {
    try {
        const response = await fetch('/api/suppliers');
        if (!response.ok) throw new Error('Nu s-au putut încărca furnizorii.');
        
        suppliersList = await response.json();
        renderSuppliers(suppliersList);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// Render Supplier Cards Checkboxes
function renderSuppliers(suppliers) {
    suppliersGrid.innerHTML = '';
    suppliers.forEach(sup => {
        const div = document.createElement('div');
        div.className = `supplier-item ${sup.enabled ? 'checked' : ''}`;
        div.dataset.id = sup.id;
        div.dataset.country = sup.country;
        
        const tags = [];
        tags.push(`<span class="tag tag-${sup.country.toLowerCase()}">${sup.country}</span>`);
        if (sup.link_only) {
            tags.push('<span class="tag tag-link">Link-only</span>');
        }

        div.innerHTML = `
            <div class="supplier-checkbox">
                <i class="fa-solid fa-check"></i>
            </div>
            <div class="supplier-info">
                <span class="supplier-name">${sup.name}</span>
                <div class="supplier-tags">${tags.join('')}</div>
            </div>
        `;

        div.addEventListener('click', () => {
            div.classList.toggle('checked');
        });

        suppliersGrid.appendChild(div);
    });
}

// Filter Suppliers UI by Country
function filterSuppliersByCountry() {
    const country = countrySelect.value;
    const items = suppliersGrid.querySelectorAll('.supplier-item');
    
    items.forEach(item => {
        if (!country || item.dataset.country === country) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

// Toggle Select All / Deselect All
function toggleAllSuppliers(checked) {
    const visibleItems = suppliersGrid.querySelectorAll('.supplier-item');
    visibleItems.forEach(item => {
        if (item.style.display !== 'none') {
            if (checked) {
                item.classList.add('checked');
            } else {
                item.classList.remove('checked');
            }
        }
    });
}

// Execute the Web Scraping Search API
async function performSearch() {
    const query = searchInput.value.trim();
    if (!query) {
        showToast('Te rog introdu un cuvânt cheie pentru căutare.', 'error');
        return;
    }

    // Gather selected suppliers
    const selectedIds = [];
    suppliersGrid.querySelectorAll('.supplier-item.checked').forEach(item => {
        if (item.style.display !== 'none') {
            selectedIds.push(item.dataset.id);
        }
    });

    if (selectedIds.length === 0) {
        showToast('Te rog selectează cel puțin un furnizor.', 'error');
        return;
    }

    // Show Loader
    loadingState.classList.remove('hidden');
    bestBuyBanner.classList.add('hidden');
    resultsSection.classList.add('hidden');

    try {
        const supplierParams = selectedIds.join(',');
        const forceScrape = document.getElementById('force-scrape-cb').checked;
        const aiOptimize = document.getElementById('ai-optimize-cb').checked;
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&suppliers=${supplierParams}&force_scrape=${forceScrape}&ai_optimize=${aiOptimize}`);
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Căutarea a eșuat.');
        }

        currentResults = await response.json();
        console.log('[BestBuyTool] API returned', currentResults.length, 'results:', currentResults);

        // Apply client-side price range filter
        const priceMin = parseFloat(document.getElementById('price-min').value) || 0;
        const priceMax = parseFloat(document.getElementById('price-max').value) || Infinity;
        
        const filteredResults = currentResults.filter(p => {
            if (p.price === 0) return true; // always show link-only
            return p.price >= priceMin && p.price <= priceMax;
        });
        console.log('[BestBuyTool] After price filter:', filteredResults.length, 'results (min:', priceMin, 'max:', priceMax, ')');

        displayResults(filteredResults, query);
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        // Hide Loader
        loadingState.classList.add('hidden');
    }
}

// Render Results
function displayResults(products, query) {
    resultsTbody.innerHTML = '';
    
    if (products.length === 0) {
        resultsCount.textContent = '0';
        resultsSection.classList.remove('hidden');
        showToast('Nu s-au găsit produse.', 'info');
        return;
    }

    resultsCount.textContent = products.length;
    resultsSection.classList.remove('hidden');

    // Find Best Buy (ignoring link-only and products with price <= 0)
    const pricedProducts = products.filter(p => p.price > 0);
    const cheapest = pricedProducts.length > 0 
        ? pricedProducts.reduce((min, p) => p.price < min.price ? p : min, pricedProducts[0]) 
        : null;

    // Display Best Buy Card
    if (cheapest) {
        bestBuyName.textContent = cheapest.name;
        bestBuyPrice.innerHTML = `${cheapest.price.toFixed(2)} ${cheapest.currency}`;
        if (cheapest.original_price && cheapest.original_currency) {
             bestBuyPrice.innerHTML += ` <span style="font-size: 0.6em; opacity: 0.8;">(${cheapest.original_price.toFixed(2)} ${cheapest.original_currency})</span>`;
        }
        bestBuySupplier.textContent = cheapest.supplier;
        bestBuyLink.href = cheapest.url;
        bestBuyBanner.classList.remove('hidden');
    }

    // Populate Table rows
    products.forEach((p, index) => {
        const tr = document.createElement('tr');
        const isBestBuy = cheapest && p.name === cheapest.name && p.price === cheapest.price;
        const isLinkOnly = p.price === 0;

        if (isBestBuy) tr.className = 'best-buy-row';
        if (isLinkOnly) tr.className = 'link-only-row';

        // Price formatting
        let priceHtml = '';
        if (isLinkOnly) {
            priceHtml = '<span class="price-col text-secondary">[LINK-ONLY]</span>';
        } else {
            if (p.original_price && p.original_currency) {
                priceHtml = `<span class="price-col">${p.price.toFixed(2)} ${p.currency} <small class="text-secondary" style="font-size: 0.8em; margin-left: 4px;">(${p.original_price.toFixed(2)} ${p.original_currency})</small></span>`;
            } else {
                priceHtml = `<span class="price-col">${p.price.toFixed(2)} ${p.currency}</span>`;
            }
            if (isBestBuy) {
                priceHtml += '<span class="table-best-buy-badge">★ Best Buy</span>';
            }
        }

        // Stock formatting
        const stockHtml = p.in_stock 
            ? '<span class="stock-indicator in-stock"><i class="fa-solid fa-circle-check"></i> În stoc</span>'
            : '<span class="stock-indicator out-of-stock"><i class="fa-solid fa-circle-xmark"></i> La comandă</span>';

        tr.innerHTML = `
            <td class="row-index">${index + 1}</td>
            <td>
                <a href="${p.url}" target="_blank" class="product-link" title="${p.name}">
                    ${p.name}
                </a>
            </td>
            <td>${priceHtml}</td>
            <td><strong>${p.supplier}</strong></td>
            <td>${stockHtml}</td>
            <td>
                <a href="${p.url}" target="_blank" class="btn-action" style="padding: 0.35rem 0.75rem; font-size: 0.8rem;">
                    Vizitează <i class="fa-solid fa-arrow-up-right-from-square"></i>
                </a>
            </td>
        `;

        resultsTbody.appendChild(tr);
    });
}

// In-Browser CSV Export
function exportResultsToCSV() {
    if (currentResults.length === 0) {
        showToast('Nu există rezultate de exportat.', 'error');
        return;
    }

    const headers = ['Nume Produs', 'Pret', 'Moneda', 'Furnizor', 'In Stoc', 'URL', 'Data Cautarii'];
    const rows = currentResults.map(p => [
        `"${p.name.replace(/"/g, '""')}"`,
        p.price,
        p.currency,
        p.supplier,
        p.in_stock ? 'DA' : 'NU',
        p.url,
        p.timestamp
    ]);

    const csvContent = "\uFEFF" + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `bestbuy_export_${new Date().toISOString().slice(0,10)}.csv`);
    link.style.visibility = 'hidden';
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showToast('Fișierul CSV a fost descărcat cu succes.', 'success');
}

// Visual Toast System
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let iconClass = 'fa-circle-info';
    if (type === 'error') iconClass = 'fa-circle-exclamation';
    if (type === 'success') iconClass = 'fa-circle-check';

    toast.innerHTML = `
        <i class="fa-solid ${iconClass}"></i>
        <span>${message}</span>
    `;

    toastContainer.appendChild(toast);

    // Auto-remove toast after 4 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
