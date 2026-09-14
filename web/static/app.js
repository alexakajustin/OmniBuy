/**
 * OmniBuy — AI Procurement Chat Controller
 */

// Global State
let suppliersList = [];
let aggregatedResults = [];
let isProcessing = false;

// DOM Elements
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatSendBtn = document.getElementById('chat-send-btn');
const clearChatBtn = document.getElementById('clear-chat-btn');
const webSearchCb = document.getElementById('web-search-cb');
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
const toastContainer = document.getElementById('toast-container');

// Startup Initialization
document.addEventListener('DOMContentLoaded', () => {
    loadSuppliers();
    setupEventListeners();
});

// Setup Event Listeners
function setupEventListeners() {
    // Chat submit
    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        sendUserMessage();
    });

    // Enter to submit (Shift+Enter for newline)
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendUserMessage();
        }
    });

    // Auto-resize textarea
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });

    // Clear chat
    clearChatBtn.addEventListener('click', () => {
        chatMessages.innerHTML = `
            <div class="message assistant">
                <div class="message-content">
                    <p><strong>Conversație resetată.</strong> Cu ce alte produse de procurement te pot ajuta?</p>
                </div>
            </div>
        `;
        aggregatedResults = [];
        bestBuyBanner.classList.add('hidden');
        resultsSection.classList.add('hidden');
    });

    // Prompt chips
    document.querySelectorAll('.prompt-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const promptText = chip.dataset.prompt;
            chatInput.value = promptText;
            chatInput.focus();
            sendUserMessage();
        });
    });

    // Suppliers select / deselect
    selectAllBtn.addEventListener('click', () => toggleAllSuppliers(true));
    deselectAllBtn.addEventListener('click', () => toggleAllSuppliers(false));

    // CSV export
    exportCsvBtn.addEventListener('click', exportResultsToCSV);
}

// Fetch configured suppliers
async function loadSuppliers() {
    try {
        const res = await fetch('/api/suppliers');
        if (!res.ok) throw new Error('Nu s-au putut încărca furnizorii.');
        suppliersList = await res.json();
        renderSuppliers(suppliersList);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// Render Supplier Badges in Sidebar
function renderSuppliers(suppliers) {
    suppliersGrid.innerHTML = '';
    suppliers.forEach(sup => {
        const item = document.createElement('div');
        item.className = `supplier-compact-item ${sup.enabled ? 'active' : ''}`;
        item.dataset.id = sup.id;
        item.dataset.country = sup.country;

        item.innerHTML = `
            <div class="supplier-compact-check">
                <i class="fa-solid fa-check"></i>
            </div>
            <span class="supplier-compact-name">${sup.name}</span>
            <span class="tag tag-${sup.country.toLowerCase()}">${sup.country}</span>
        `;

        item.addEventListener('click', () => {
            item.classList.toggle('active');
        });

        suppliersGrid.appendChild(item);
    });
}

function toggleAllSuppliers(active) {
    document.querySelectorAll('.supplier-compact-item').forEach(item => {
        if (active) item.classList.add('active');
        else item.classList.remove('active');
    });
}

function getSelectedSupplierIds() {
    const selected = [];
    document.querySelectorAll('.supplier-compact-item.active').forEach(item => {
        selected.push(item.dataset.id);
    });
    return selected;
}

// Send User Message & Handle Streaming AI Agent
async function sendUserMessage() {
    const prompt = chatInput.value.trim();
    if (!prompt || isProcessing) return;

    // Reset input height
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Append User Message to Chat
    appendMessage('user', prompt);

    // Prepare Assistant Bubble with live thinking container
    const assistantBubble = appendMessage('assistant', '', true);
    const thinkingBox = assistantBubble.querySelector('.agent-thoughts');
    const contentBox = assistantBubble.querySelector('.markdown-body');

    isProcessing = true;
    chatSendBtn.disabled = true;

    try {
        const payload = {
            prompt: prompt,
            country: countrySelect.value || null,
            suppliers: getSelectedSupplierIds(),
            include_web_search: webSearchCb.checked,
        };

        const response = await fetch('/api/chat/procure', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            throw new Error(`Eroare de la server: ${response.statusText}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop(); // Keep partial line in buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.replace('data: ', '').trim();
                    if (!jsonStr) continue;

                    try {
                        const eventData = JSON.parse(jsonStr);
                        handleAgentEvent(eventData, thinkingBox, contentBox);
                    } catch (e) {
                        console.error('SSE JSON parse error:', e, jsonStr);
                    }
                }
            }
        }
    } catch (err) {
        showToast(err.message, 'error');
        contentBox.innerHTML = `<p style="color: var(--danger);"><i class="fa-solid fa-triangle-exclamation"></i> Eroare: ${err.message}</p>`;
    } finally {
        isProcessing = false;
        chatSendBtn.disabled = false;
        chatInput.focus();
    }
}

// Append a message node to the chat container
function appendMessage(sender, text, isStreaming = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;

    if (sender === 'user') {
        msgDiv.innerHTML = `<div class="message-content"><p>${escapeHtml(text)}</p></div>`;
    } else {
        msgDiv.innerHTML = `
            <div class="message-content">
                ${isStreaming ? '<div class="agent-thoughts"></div>' : ''}
                <div class="markdown-body">${text ? renderMarkdown(text) : ''}</div>
                <div class="product-cards-container"></div>
            </div>
        `;
    }

    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return msgDiv;
}

// Handle Event Updates from SSE Stream
function handleAgentEvent(data, thinkingBox, contentBox) {
    if (data.type === 'thought') {
        // Add or update thought pill
        const pill = document.createElement('div');
        pill.className = 'thought-pill';
        pill.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${escapeHtml(data.message)}`;
        
        // Mark previous pills as completed
        thinkingBox.querySelectorAll('.thought-pill').forEach(p => {
            const icon = p.querySelector('i');
            if (icon) {
                icon.className = 'fa-solid fa-check text-success';
            }
        });

        thinkingBox.appendChild(pill);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    } 
    else if (data.type === 'complete') {
        // Mark all thoughts completed
        thinkingBox.querySelectorAll('.thought-pill').forEach(p => {
            const icon = p.querySelector('i');
            if (icon) icon.className = 'fa-solid fa-check text-success';
        });

        // Render Markdown content
        if (data.markdown) {
            contentBox.innerHTML = renderMarkdown(data.markdown);
        }

        // Update aggregated table and spotlight banner
        if (data.products && data.products.length > 0) {
            aggregatedResults = data.products;
            updateSpotlightAndTable(aggregatedResults);
        }

        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    else if (data.type === 'error') {
        contentBox.innerHTML += `<p style="color: var(--danger);"><i class="fa-solid fa-circle-exclamation"></i> ${escapeHtml(data.message)}</p>`;
    }
}

// Update Spotlight Banner and Results Table
function updateSpotlightAndTable(products) {
    // 1. Spotlight Banner (Best product by composite_score)
    const scored = products.filter(p => p.price > 0 && (p.composite_score || 0) > 0);
    if (scored.length > 0) {
        const best = scored[0];
        const scoreVal = Math.round(best.composite_score || 90);
        bestBuyName.textContent = best.name;
        bestBuyPrice.textContent = `${best.price.toFixed(2)} RON`;
        bestBuySupplier.innerHTML = `<span class="score-pill">⭐ Scor: ${scoreVal}/100</span> • ${escapeHtml(best.supplier)}`;
        bestBuyLink.href = best.url;
        bestBuyBanner.classList.remove('hidden');
    }

    // 2. Table
    resultsCount.textContent = products.length;
    resultsTbody.innerHTML = '';

    products.forEach((prod, index) => {
        const tr = document.createElement('tr');

        const isBestBuy = index === 0 && (prod.composite_score || 0) > 0;
        const priceDisplay = prod.price > 0 
            ? `<span class="price-val ${isBestBuy ? 'best-price' : ''}">${prod.price.toFixed(2)} RON</span>` 
            : '<span class="price-link">Preț pe site</span>';

        const isWeb = prod.supplier.startsWith('[Web]');
        const supplierBadge = isWeb 
            ? `<span class="supplier-pill supplier-web"><i class="fa-solid fa-globe"></i> ${escapeHtml(prod.supplier.replace('[Web] ', ''))}</span>`
            : `<span class="supplier-pill supplier-b2b"><i class="fa-solid fa-store"></i> ${escapeHtml(prod.supplier)}</span>`;

        const scoreBadge = (prod.composite_score && prod.composite_score > 0)
            ? `<span class="spec-verified-tag ${isBestBuy ? 'tag-best-score' : ''}"><i class="fa-solid fa-award"></i> ${Math.round(prod.composite_score)}% Calitate/Preț</span>`
            : `<span class="spec-verified-tag"><i class="fa-solid fa-shield-check"></i> Conform</span>`;

        tr.innerHTML = `
            <td>${index + 1}</td>
            <td class="product-title-cell">
                <a href="${prod.url}" target="_blank" class="table-prod-link">${escapeHtml(prod.name)}</a>
            </td>
            <td>${priceDisplay}</td>
            <td>${supplierBadge}</td>
            <td>${scoreBadge}</td>
            <td>
                <a href="${prod.url}" target="_blank" class="btn-action-table">
                    Vezi <i class="fa-solid fa-arrow-up-right-from-square"></i>
                </a>
            </td>
        `;

        resultsTbody.appendChild(tr);
    });

    resultsSection.classList.remove('hidden');
}

// Export Results to CSV
function exportResultsToCSV() {
    if (!aggregatedResults || aggregatedResults.length === 0) {
        showToast('Nu există rezultate de exportat.', 'error');
        return;
    }

    let csv = 'Nr,Produs,Pret (RON),Furnizor,Link\n';
    aggregatedResults.forEach((p, idx) => {
        const cleanName = `"${(p.name || '').replace(/"/g, '""')}"`;
        const cleanSupplier = `"${(p.supplier || '').replace(/"/g, '""')}"`;
        csv += `${idx + 1},${cleanName},${p.price || 0},${cleanSupplier},"${p.url}"\n`;
    });

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `omnibuy_achizitii_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Fișierul CSV a fost descărcat!', 'info');
}

// Markdown helper
function renderMarkdown(md) {
    if (window.marked) {
        return window.marked.parse(md);
    }
    return md.replace(/\n/g, '<br>');
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Toast Notification
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = 'fa-info-circle';
    if (type === 'error') icon = 'fa-circle-exclamation';
    if (type === 'success') icon = 'fa-circle-check';

    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${escapeHtml(message)}</span>`;
    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
