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

const searchInfo = document.getElementById('search-info');
const loadingState = document.getElementById('loading-state');
const toastContainer = document.getElementById('toast-container');

// Scraped names/URLs come from third-party sites — never put them into innerHTML unescaped.
function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Only allow http(s) links (blocks javascript: and similar schemes).
function safeUrl(url) {
    try {
        const parsed = new URL(url, window.location.origin);
        return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : '#';
    } catch {
        return '#';
    }
}

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
        tags.push(`<span class="tag tag-${escapeHtml(sup.country.toLowerCase())}">${escapeHtml(sup.country)}</span>`);
        if (sup.link_only) {
            tags.push('<span class="tag tag-link">Link-only</span>');
        }

        div.innerHTML = `
            <div class="supplier-checkbox">
                <i class="fa-solid fa-check"></i>
            </div>
            <div class="supplier-info">
                <span class="supplier-name">${escapeHtml(sup.name)}</span>
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
    searchBtn.disabled = true;

    try {
        const params = new URLSearchParams({
            v: 2,
            q: query,
            suppliers: selectedIds.join(','),
            force_scrape: document.getElementById('force-scrape-cb').checked,
            ai_optimize: document.getElementById('ai-optimize-cb').checked,
        });
        const response = await fetch(`/api/search?${params}`);

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            const detail = typeof errData.detail === 'string' ? errData.detail : null;
            throw new Error(detail || `Căutarea a eșuat (HTTP ${response.status}).`);
        }

        const data = await response.json();
        currentResults = Array.isArray(data.results) ? data.results : [];
        console.log('[BestBuyTool] API returned', currentResults.length, 'results:', data);

        // Apply client-side price range filter (only to products that have a price)
        const priceMin = parseFloat(document.getElementById('price-min').value) || 0;
        const priceMax = parseFloat(document.getElementById('price-max').value) || Infinity;

        const filteredResults = currentResults.filter(p => {
            if (p.is_link || p.price <= 0) return true;
            return p.price >= priceMin && p.price <= priceMax;
        });

        renderSearchInfo(data);
        displayResults(filteredResults, query);
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        // Hide Loader
        loadingState.classList.add('hidden');
        searchBtn.disabled = false;
    }
}

// Show what was actually searched (AI term) and how each supplier responded
function renderSearchInfo(data) {
    const lines = [];

    if (data.ai) {
        if (data.effective_query !== data.query) {
            lines.push(`<div class="search-info-line"><i class="fa-solid fa-brain"></i>
                AI (${escapeHtml(data.ai.source)}) a căutat: <strong>${escapeHtml(data.effective_query)}</strong>
                <span>(original: ${escapeHtml(data.query)})</span></div>`);
        } else if (!data.ai.note) {
            lines.push(`<div class="search-info-line"><i class="fa-solid fa-brain"></i>
                AI a păstrat căutarea originală: <strong>${escapeHtml(data.query)}</strong></div>`);
        }
        if (data.ai.note) {
            lines.push(`<div class="search-info-line warn"><i class="fa-solid fa-triangle-exclamation"></i>
                ${escapeHtml(data.ai.note)}</div>`);
        }
    }

    const statusLabels = { ok: 'rezultate', link: 'doar link', irrelevant: 'nimic relevant', error: 'eroare' };
    const chips = (data.suppliers || []).map(s => {
        let label = s.status === 'ok' ? `${s.count} ${statusLabels.ok}` : statusLabels[s.status] || s.status;
        if (data.ai && s.query_used && s.query_used !== data.effective_query) {
            label += ', reîncercat cu căutarea originală';
        }
        return `<span class="supplier-chip ${escapeHtml(s.status)}">${escapeHtml(s.supplier)}: ${escapeHtml(label)}</span>`;
    });
    if (chips.length) {
        lines.push(`<div class="search-info-line">${chips.join('')}</div>`);
    }

    searchInfo.innerHTML = lines.join('');
    searchInfo.classList.toggle('hidden', lines.length === 0);
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
    // Prefer products that are in stock; fall back to the cheapest overall.
    const pricedProducts = products.filter(p => !p.is_link && p.price > 0);
    const inStock = pricedProducts.filter(p => p.in_stock);
    const candidates = inStock.length > 0 ? inStock : pricedProducts;
    const cheapest = candidates.length > 0
        ? candidates.reduce((min, p) => p.price < min.price ? p : min, candidates[0])
        : null;

    // Display Best Buy Card
    if (cheapest) {
        bestBuyName.textContent = cheapest.name;
        bestBuyPrice.innerHTML = `${cheapest.price.toFixed(2)} ${cheapest.currency}`;
        if (cheapest.original_price && cheapest.original_currency) {
             bestBuyPrice.innerHTML += ` <span style="font-size: 0.6em; opacity: 0.8;">(${cheapest.original_price.toFixed(2)} ${cheapest.original_currency})</span>`;
        }
        bestBuySupplier.textContent = cheapest.supplier;
        bestBuyLink.href = safeUrl(cheapest.url);
        bestBuyBanner.classList.remove('hidden');
    }

    // Populate Table rows
    products.forEach((p, index) => {
        const tr = document.createElement('tr');
        const isBestBuy = p === cheapest;
        const isLinkOnly = p.is_link;
        const url = escapeHtml(safeUrl(p.url));
        const name = escapeHtml(p.name);

        if (isBestBuy) tr.className = 'best-buy-row';
        if (isLinkOnly) tr.className = 'link-only-row';

        // Price formatting
        let priceHtml = '';
        if (isLinkOnly) {
            priceHtml = '<span class="price-col text-secondary">[LINK-ONLY]</span>';
        } else if (p.price <= 0) {
            priceHtml = '<span class="price-col text-secondary">Preț indisponibil</span>';
        } else {
            if (p.original_price && p.original_currency) {
                priceHtml = `<span class="price-col">${p.price.toFixed(2)} ${escapeHtml(p.currency)} <small class="text-secondary" style="font-size: 0.8em; margin-left: 4px;">(${p.original_price.toFixed(2)} ${escapeHtml(p.original_currency)})</small></span>`;
            } else {
                priceHtml = `<span class="price-col">${p.price.toFixed(2)} ${escapeHtml(p.currency)}</span>`;
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
                <a href="${url}" target="_blank" rel="noopener noreferrer" class="product-link" title="${name}">
                    ${name}
                </a>
            </td>
            <td>${priceHtml}</td>
            <td><strong>${escapeHtml(p.supplier)}</strong></td>
            <td>${stockHtml}</td>
            <td>
                <a href="${url}" target="_blank" rel="noopener noreferrer" class="btn-action" style="padding: 0.35rem 0.75rem; font-size: 0.8rem;">
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
    const csvCell = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const rows = currentResults.map(p => [
        p.name,
        p.is_link ? '' : p.price,
        p.currency,
        p.supplier,
        p.in_stock ? 'DA' : 'NU',
        p.url,
        p.timestamp
    ].map(csvCell));

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
        <span>${escapeHtml(message)}</span>
    `;

    toastContainer.appendChild(toast);

    // Auto-remove toast after 4 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
