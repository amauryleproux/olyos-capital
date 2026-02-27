// Trade Modal Functions
let currentTradeType = 'BUY';
let currentMaxQty = 0;

function openTradeModal(ticker='', name='', type='BUY', maxQty=0) {
    currentTradeType = type;
    currentMaxQty = maxQty || 0;

    document.getElementById('trade-ticker').value = ticker;
    document.getElementById('trade-qty').value = '';
    document.getElementById('trade-price').value = '';
    document.getElementById('trade-date').value = new Date().toISOString().split('T')[0];
    document.getElementById('trade-fees').value = '0';
    document.getElementById('trade-notes').value = '';
    document.getElementById('trade-summary').style.display = 'none';

    setTradeType(type);

    // If selling, fetch current qty
    if (type === 'SELL' && ticker) {
        fetchTickerQty(ticker);
    }

    document.getElementById('trade-modal').style.display = 'flex';
    if (!ticker) {
        document.getElementById('trade-ticker').focus();
    } else {
        document.getElementById('trade-qty').focus();
    }
}

function closeTradeModal() {
    document.getElementById('trade-modal').style.display = 'none';
}

function setTradeType(type) {
    currentTradeType = type;
    const buyBtn = document.getElementById('trade-type-buy');
    const sellBtn = document.getElementById('trade-type-sell');
    const confirmBtn = document.getElementById('trade-confirm-btn');
    const maxQtyEl = document.getElementById('trade-max-qty');
    const summary = document.getElementById('trade-summary');

    if (type === 'BUY') {
        buyBtn.classList.add('active');
        sellBtn.classList.remove('active');
        confirmBtn.classList.remove('sell-mode');
        confirmBtn.textContent = 'CONFIRM BUY';
        maxQtyEl.style.display = 'none';
        summary.classList.remove('sell');
        summary.classList.add('buy');
    } else {
        buyBtn.classList.remove('active');
        sellBtn.classList.add('active');
        confirmBtn.classList.add('sell-mode');
        confirmBtn.textContent = 'CONFIRM SELL';
        if (currentMaxQty > 0) {
            document.getElementById('max-qty-val').textContent = currentMaxQty.toFixed(2);
            maxQtyEl.style.display = 'inline';
        }
        summary.classList.remove('buy');
        summary.classList.add('sell');
    }
    updateTradeSummary();
}

function fetchTickerQty(ticker) {
    fetch(`/?action=get_ticker_qty&ticker=${ ticker }`)
        .then(r => r.json())
        .then(data => {
            if (data.success && data.data) {
                currentMaxQty = data.data.quantity || 0;
                document.getElementById('max-qty-val').textContent = currentMaxQty.toFixed(2);
                if (currentTradeType === 'SELL' && currentMaxQty > 0) {
                    document.getElementById('trade-max-qty').style.display = 'inline';
                }
            }
        })
        .catch(err => console.error('Error fetching qty:', err));
}

function fillMaxQty() {
    document.getElementById('trade-qty').value = currentMaxQty;
    updateTradeSummary();
}

function updateTradeSummary() {
    const qty = parseFloat(document.getElementById('trade-qty').value) || 0;
    const price = parseFloat(document.getElementById('trade-price').value) || 0;
    const fees = parseFloat(document.getElementById('trade-fees').value) || 0;
    const summary = document.getElementById('trade-summary');

    if (qty > 0 && price > 0) {
        const total = qty * price;
        const netTotal = currentTradeType === 'BUY' ? total + fees : total - fees;
        const action = currentTradeType === 'BUY' ? 'Cost' : 'Proceeds';
        summary.innerHTML = `<span style="color:#888">${ currentTradeType }</span> <span style="color:#fff">${ qty }</span> shares @ <span style="color:#fff">€${price.toFixed(2)}</span> = <span style="color:${currentTradeType === 'BUY' ? '#00ff00' : '#ff3333'}">€${netTotal.toFixed(2)}</span> <span style="color:#666">(${ action })</span>`;
        summary.style.display = 'block';
    } else {
        summary.style.display = 'none';
    }
}

// Update summary on input change
document.getElementById('trade-qty')?.addEventListener('input', updateTradeSummary);
document.getElementById('trade-price')?.addEventListener('input', updateTradeSummary);
document.getElementById('trade-fees')?.addEventListener('input', updateTradeSummary);

// Fetch qty when ticker changes (for sell)
document.getElementById('trade-ticker')?.addEventListener('change', function() {
    if (currentTradeType === 'SELL' && this.value) {
        fetchTickerQty(this.value);
    }
});

function confirmTrade() {
    const ticker = document.getElementById('trade-ticker').value.trim().toUpperCase();
    const qty = parseFloat(document.getElementById('trade-qty').value) || 0;
    const price = parseFloat(document.getElementById('trade-price').value) || 0;
    const date = document.getElementById('trade-date').value;
    const fees = parseFloat(document.getElementById('trade-fees').value) || 0;
    const notes = document.getElementById('trade-notes').value;

    if (!ticker) { alert('Ticker is required'); return; }
    if (qty <= 0) { alert('Quantity must be > 0'); return; }
    if (price <= 0) { alert('Price must be > 0'); return; }

    // Validate sell quantity
    if (currentTradeType === 'SELL' && qty > currentMaxQty) {
        alert(`Cannot sell ${ qty } shares. You only have ${currentMaxQty.toFixed(2)} shares.`);
        return;
    }

    const confirmBtn = document.getElementById('trade-confirm-btn');
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Processing...';

    const url = `/?action=add_transaction&ticker=${ ticker }&type=${ currentTradeType }&date=${ date }&quantity=${ qty }&price=${ price }&fees=${ fees }&notes=${encodeURIComponent(notes)}`;

    fetch(url)
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                closeTradeModal();
                alert(`${ currentTradeType } order executed: ${ qty } ${ ticker } @ €${price.toFixed(2)}`);
                location.reload();
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
                confirmBtn.disabled = false;
                confirmBtn.textContent = currentTradeType === 'BUY' ? 'CONFIRM BUY' : 'CONFIRM SELL';
            }
        })
        .catch(err => {
            alert('Error: ' + err.message);
            confirmBtn.disabled = false;
            confirmBtn.textContent = currentTradeType === 'BUY' ? 'CONFIRM BUY' : 'CONFIRM SELL';
        });
}

// ═══ PDF REPORT GENERATION ═══
function generateReport() {
    const now = new Date();
    const month = now.getMonth() + 1;
    const year = now.getFullYear();

    // Show loading indicator
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = '⏳ GEN...';
    btn.disabled = true;

    // Generate and download report
    fetch(`/?action=generate_report&month=${ month }&year=${ year }`)
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || 'Failed to generate report');
                });
            }
            return response.blob();
        })
        .then(blob => {
            // Create download link
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `report_${ year }_${String(month).padStart(2, '0')}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();

            // Reset button
            btn.textContent = originalText;
            btn.disabled = false;
        })
        .catch(err => {
            alert('Error generating report: ' + err.message);
            btn.textContent = originalText;
            btn.disabled = false;
        });
}

// ═══ INSIDER TRADING PANEL ═══
let insiderPanelVisible = false;

function toggleInsiderPanel() {
    const panel = document.getElementById('insiderPanel');
    if (!panel) {
        createInsiderPanel();
        loadInsiderFeed();
    } else {
        insiderPanelVisible = !insiderPanelVisible;
        panel.style.display = insiderPanelVisible ? 'block' : 'none';
        if (insiderPanelVisible) loadInsiderFeed();
    }
}

function createInsiderPanel() {
    const panel = document.createElement('div');
    panel.id = 'insiderPanel';
    panel.style.cssText = `
        position: fixed;
        top: 60px;
        right: 20px;
        width: 420px;
        max-height: 80vh;
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #22c55e;
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(34, 197, 94, 0.2);
        z-index: 9999;
        overflow: hidden;
        font-family: 'Consolas', 'Monaco', monospace;
    `;

    panel.innerHTML = `
        <div style="padding:12px 16px;background:#0f1419;border-bottom:1px solid #22c55e;display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#22c55e;font-weight:bold;font-size:14px;">📊 INSIDER ACTIVITY</span>
            <div>
                <select id="insiderScope" onchange="loadInsiderFeed()" style="background:#1a1f25;color:#9ca3af;border:1px solid #374151;border-radius:4px;padding:4px 8px;font-size:12px;margin-right:8px;">
                    <option value="portfolio">Portfolio</option>
                    <option value="watchlist">Watchlist</option>
                    <option value="all">All</option>
                </select>
                <button onclick="loadInsiderFeed()" style="background:none;border:none;color:#22c55e;cursor:pointer;font-size:14px;">🔄</button>
                <button onclick="toggleInsiderPanel()" style="background:none;border:none;color:#6b7280;cursor:pointer;font-size:18px;margin-left:8px;">×</button>
            </div>
        </div>
        <div id="insiderFeedContent" style="padding:12px;max-height:calc(80vh - 60px);overflow-y:auto;">
            <div style="color:#6b7280;text-align:center;padding:20px;">Loading...</div>
        </div>
    `;

    document.body.appendChild(panel);
    insiderPanelVisible = true;
}

function loadInsiderFeed() {
    const content = document.getElementById('insiderFeedContent');
    const scope = document.getElementById('insiderScope')?.value || 'portfolio';

    content.innerHTML = '<div style="color:#6b7280;text-align:center;padding:20px;">⏳ Loading insider data...</div>';

    fetch(`/?action=insider_feed&scope=${ scope }&limit=30`)
        .then(r => r.json())
        .then(data => {
            if (!data.success || !data.data.transactions.length) {
                content.innerHTML = '<div style="color:#6b7280;text-align:center;padding:20px;">No insider transactions found</div>';
                return;
            }

            let html = '';
            const transactions = data.data.transactions;

            // Group by date
            let currentDate = '';
            for (const t of transactions) {
                if (t.date !== currentDate) {
                    currentDate = t.date;
                    html += `<div style="color:#6b7280;font-size:10px;margin:12px 0 6px 0;text-transform:uppercase;border-bottom:1px solid #1f2937;padding-bottom:4px;">${formatDate(t.date)}</div>`;
                }

                const isBuy = t.transaction_type === 'BUY';
                const color = isBuy ? '#22c55e' : '#ef4444';
                const icon = isBuy ? '📈' : '📉';
                const value = formatMoney(t.value);

                html += `
                    <div style="padding:8px;margin:4px 0;background:#1a1f25;border-radius:6px;border-left:3px solid ${ color };">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                            <div>
                                <span style="color:#ffd700;font-weight:bold;">${t.ticker}</span>
                                <span style="color:${ color };font-size:12px;margin-left:6px;">${ icon } ${isBuy ? 'ACHAT' : 'VENTE'}</span>
                            </div>
                            <span style="color:${ color };font-weight:bold;">${ value }</span>
                        </div>
                        <div style="color:#9ca3af;font-size:11px;margin-top:4px;">
                            ${t.insider_name} <span style="color:#6b7280;">(${t.insider_title || 'Director'})</span>
                        </div>
                        <div style="color:#6b7280;font-size:10px;margin-top:2px;">
                            ${t.shares.toLocaleString()} actions @ ${t.price.toFixed(2)}€
                        </div>
                    </div>
                `;
            }

            content.innerHTML = html || '<div style="color:#6b7280;text-align:center;padding:20px;">No data</div>';
        })
        .catch(err => {
            content.innerHTML = `<div style="color:#ef4444;text-align:center;padding:20px;">Error: ${err.message}</div>`;
        });
}

function formatDate(dateStr) {
    const d = new Date(dateStr);
    const options = { day: 'numeric', month: 'short', year: 'numeric' };
    return d.toLocaleDateString('fr-FR', options);
}

function formatMoney(val) {
    if (val >= 1000000) return (val / 1000000).toFixed(1) + 'M€';
    if (val >= 1000) return (val / 1000).toFixed(0) + 'k€';
    return val.toFixed(0) + '€';
}

// Keyboard shortcut for F8
document.addEventListener('keydown', function(e) {
    if (e.key === 'F8') {
        e.preventDefault();
        toggleInsiderPanel();
    }
});

// ═══ REBALANCING PANEL ═══
let rebalancePanelVisible = false;

function toggleRebalancePanel() {
    const panel = document.getElementById('rebalancePanel');
    if (!panel) {
        createRebalancePanel();
        loadRebalanceAnalysis();
    } else {
        rebalancePanelVisible = !rebalancePanelVisible;
        panel.style.display = rebalancePanelVisible ? 'block' : 'none';
        if (rebalancePanelVisible) loadRebalanceAnalysis();
    }
}

function createRebalancePanel() {
    const panel = document.createElement('div');
    panel.id = 'rebalancePanel';
    panel.style.cssText = `
        position: fixed;
        top: 60px;
        right: 460px;
        width: 520px;
        max-height: 85vh;
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #f59e0b;
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(245, 158, 11, 0.2);
        z-index: 9998;
        overflow: hidden;
        font-family: 'Consolas', 'Monaco', monospace;
    `;

    panel.innerHTML = `
        <div style="padding:12px 16px;background:#0f1419;border-bottom:1px solid #f59e0b;display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#f59e0b;font-weight:bold;font-size:14px;">⚖️ REBALANCING</span>
            <div>
                <select id="rebalanceMethod" onchange="loadRebalanceAnalysis()" style="background:#1a1f25;color:#9ca3af;border:1px solid #374151;border-radius:4px;padding:4px 8px;font-size:12px;margin-right:8px;">
                    <option value="equal">Équipondéré</option>
                    <option value="score">Pondéré Score</option>
                    <option value="conviction">Conviction</option>
                </select>
                <button onclick="loadRebalanceAnalysis()" style="background:none;border:none;color:#f59e0b;cursor:pointer;font-size:14px;">🔄</button>
                <button onclick="toggleRebalancePanel()" style="background:none;border:none;color:#6b7280;cursor:pointer;font-size:18px;margin-left:8px;">×</button>
            </div>
        </div>
        <div id="rebalanceContent" style="padding:12px;max-height:calc(85vh - 60px);overflow-y:auto;">
            <div style="color:#6b7280;text-align:center;padding:20px;">Loading...</div>
        </div>
    `;

    document.body.appendChild(panel);
    rebalancePanelVisible = true;
}

function loadRebalanceAnalysis() {
    const content = document.getElementById('rebalanceContent');
    const method = document.getElementById('rebalanceMethod')?.value || 'equal';

    content.innerHTML = '<div style="color:#6b7280;text-align:center;padding:20px;">⏳ Analyzing portfolio...</div>';

    Promise.all([
        fetch('/?action=rebalance_analyze').then(r => r.json()),
        fetch(`/?action=rebalance_propose&method=${ method }`).then(r => r.json())
    ])
    .then(([analysis, proposals]) => {
        if (!analysis.success || !proposals.success) {
            content.innerHTML = '<div style="color:#ef4444;text-align:center;padding:20px;">Error loading data</div>';
            return;
        }

        const data = analysis.data;
        const propData = proposals.data;
        let html = '';

        // Summary stats
        html += `
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px;">
                <div style="background:#1a1f25;padding:10px;border-radius:6px;text-align:center;">
                    <div style="color:#6b7280;font-size:10px;text-transform:uppercase;">Portfolio</div>
                    <div style="color:#ffd700;font-size:18px;font-weight:bold;">${formatMoney(data.total_portfolio_value)}</div>
                </div>
                <div style="background:#1a1f25;padding:10px;border-radius:6px;text-align:center;">
                    <div style="color:#6b7280;font-size:10px;text-transform:uppercase;">Positions</div>
                    <div style="color:#22d3ee;font-size:18px;font-weight:bold;">${data.num_positions}</div>
                </div>
                <div style="background:#1a1f25;padding:10px;border-radius:6px;text-align:center;">
                    <div style="color:#6b7280;font-size:10px;text-transform:uppercase;">Statut</div>
                    <div style="color:${data.is_balanced ? '#22c55e' : '#f59e0b'};font-size:18px;font-weight:bold;">
                        ${data.is_balanced ? '✓ OK' : '⚠️ ' + data.imbalances.length}
                    </div>
                </div>
            </div>
        `;

        // Imbalances section
        if (data.imbalances && data.imbalances.length > 0) {
            html += `<div style="color:#f59e0b;font-size:12px;font-weight:bold;margin:12px 0 8px 0;text-transform:uppercase;">⚠️ Déséquilibres détectés</div>`;
            for (const imb of data.imbalances) {
                const color = imb.severity === 'critical' ? '#ef4444' : '#f59e0b';
                const icon = imb.severity === 'critical' ? '🔴' : '🟡';
                html += `
                    <div style="padding:8px;margin:4px 0;background:#1a1f25;border-radius:6px;border-left:3px solid ${ color };">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="color:#ffd700;font-weight:bold;">${ icon } ${imb.ticker}</span>
                            <span style="color:${ color };font-size:11px;padding:2px 6px;background:rgba(245,158,11,0.1);border-radius:4px;">${imb.imbalance_type}</span>
                        </div>
                        <div style="color:#9ca3af;font-size:11px;margin-top:4px;">${imb.message}</div>
                        <div style="color:#6b7280;font-size:10px;margin-top:2px;">
                            Action suggérée: <span style="color:#22d3ee;">${imb.suggested_action}</span>
                        </div>
                    </div>
                `;
            }
        }

        // Trade proposals section
        if (propData.proposals && propData.proposals.length > 0) {
            html += `
                <div style="color:#22d3ee;font-size:12px;font-weight:bold;margin:16px 0 8px 0;text-transform:uppercase;">📋 Propositions de trades</div>
                <div style="display:flex;gap:12px;margin-bottom:12px;">
                    <div style="flex:1;background:#0f2818;padding:8px;border-radius:6px;text-align:center;border:1px solid #22c55e30;">
                        <div style="color:#6b7280;font-size:10px;">À acheter</div>
                        <div style="color:#22c55e;font-weight:bold;">${formatMoney(propData.total_buy)}</div>
                    </div>
                    <div style="flex:1;background:#280f0f;padding:8px;border-radius:6px;text-align:center;border:1px solid #ef444430;">
                        <div style="color:#6b7280;font-size:10px;">À vendre</div>
                        <div style="color:#ef4444;font-weight:bold;">${formatMoney(propData.total_sell)}</div>
                    </div>
                    <div style="flex:1;background:#1a1f25;padding:8px;border-radius:6px;text-align:center;">
                        <div style="color:#6b7280;font-size:10px;">Net</div>
                        <div style="color:#ffd700;font-weight:bold;">${formatMoney(propData.net_flow)}</div>
                    </div>
                </div>
            `;

            for (const trade of propData.proposals) {
                const isBuy = trade.action === 'ADD';
                const color = isBuy ? '#22c55e' : (trade.action === 'SELL' ? '#ef4444' : '#f59e0b');
                const arrow = trade.deviation > 0 ? '↑' : '↓';

                html += `
                    <div style="padding:8px;margin:4px 0;background:#1a1f25;border-radius:6px;border-left:3px solid ${ color };">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div>
                                <span style="color:#ffd700;font-weight:bold;">${trade.ticker}</span>
                                <span style="color:${ color };font-size:11px;margin-left:6px;">${trade.action}</span>
                            </div>
                            <span style="color:${ color };font-weight:bold;">${trade.trade_value > 0 ? '+' : ''}${formatMoney(Math.abs(trade.trade_value))}</span>
                        </div>
                        <div style="color:#9ca3af;font-size:11px;margin-top:4px;">
                            ${trade.current_weight.toFixed(1)}% ${ arrow } ${trade.target_weight.toFixed(1)}%
                            <span style="color:#6b7280;margin-left:8px;">(${trade.deviation > 0 ? '+' : ''}${trade.deviation.toFixed(1)}%)</span>
                        </div>
                        <div style="color:#6b7280;font-size:10px;margin-top:2px;">
                            ~${Math.abs(trade.shares_to_trade).toFixed(0)} actions @ ${trade.current_price.toFixed(2)}€
                        </div>
                    </div>
                `;
            }
        } else {
            html += `<div style="color:#22c55e;text-align:center;padding:20px;background:#0f2818;border-radius:6px;margin-top:12px;">
                ✓ Portfolio équilibré - Aucune action requise
            </div>`;
        }

        content.innerHTML = html;
    })
    .catch(err => {
        content.innerHTML = `<div style="color:#ef4444;text-align:center;padding:20px;">Error: ${err.message}</div>`;
    });
}

// Keyboard shortcut for F9
document.addEventListener('keydown', function(e) {
    if (e.key === 'F9') {
        e.preventDefault();
        toggleRebalancePanel();
    }
});

// ═══ HEATMAP TREEMAP PANEL ═══
let heatmapPanelVisible = false;
let heatmapMetric = 'pnl_pct';
let heatmapGrouping = 'sector';
let heatmapData = null;

function toggleHeatmapPanel() {
    const panel = document.getElementById('heatmapPanel');
    if (!panel) {
        createHeatmapPanel();
        loadHeatmapData();
    } else {
        heatmapPanelVisible = !heatmapPanelVisible;
        panel.style.display = heatmapPanelVisible ? 'block' : 'none';
        if (heatmapPanelVisible) loadHeatmapData();
    }
}

function createHeatmapPanel() {
    const panel = document.createElement('div');
    panel.id = 'heatmapPanel';
    panel.style.cssText = `
        position: fixed;
        top: 50px;
        left: 50%;
        transform: translateX(-50%);
        width: 90vw;
        max-width: 1400px;
        height: 80vh;
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #a855f7;
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(168, 85, 247, 0.3);
        z-index: 10000;
        overflow: hidden;
        font-family: 'Consolas', 'Monaco', monospace;
    `;

    panel.innerHTML = `
        <div style="padding:12px 16px;background:#0f1419;border-bottom:1px solid #a855f7;display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#a855f7;font-weight:bold;font-size:14px;">📊 MARKET HEATMAP</span>
            <div style="display:flex;gap:12px;align-items:center;">
                <div>
                    <label style="color:#6b7280;font-size:11px;margin-right:4px;">Couleur:</label>
                    <select id="heatmapMetric" onchange="changeHeatmapMetric(this.value)" style="background:#1a1f25;color:#9ca3af;border:1px solid #374151;border-radius:4px;padding:4px 8px;font-size:11px;">
                        <option value="pnl_pct" selected>P&L Total</option>
                        <option value="change_pct">Perf Jour</option>
                        <option value="ytd_pct">Perf YTD</option>
                        <option value="score">Score Higgons</option>
                        <option value="pe">PE Ratio</option>
                        <option value="pcf">P/CF Ratio</option>
                    </select>
                </div>
                <div>
                    <label style="color:#6b7280;font-size:11px;margin-right:4px;">Grouper:</label>
                    <select id="heatmapGrouping" onchange="changeHeatmapGrouping(this.value)" style="background:#1a1f25;color:#9ca3af;border:1px solid #374151;border-radius:4px;padding:4px 8px;font-size:11px;">
                        <option value="sector">Secteur</option>
                        <option value="country">Pays</option>
                        <option value="flat">Aucun</option>
                    </select>
                </div>
                <button onclick="loadHeatmapData()" style="background:none;border:none;color:#a855f7;cursor:pointer;font-size:14px;">🔄</button>
                <button onclick="toggleHeatmapPanel()" style="background:none;border:none;color:#6b7280;cursor:pointer;font-size:18px;">×</button>
            </div>
        </div>
        <div id="heatmapContainer" style="width:100%;height:calc(100% - 50px);position:relative;">
            <div style="color:#6b7280;text-align:center;padding:40px;">Loading...</div>
        </div>
        <div id="heatmapTooltip" style="position:fixed;display:none;background:#1a1f25;border:1px solid #374151;border-radius:6px;padding:12px;box-shadow:0 4px 12px rgba(0,0,0,0.5);z-index:10001;pointer-events:none;min-width:200px;"></div>
    `;

    document.body.appendChild(panel);
    heatmapPanelVisible = true;
}

function changeHeatmapMetric(metric) {
    heatmapMetric = metric;
    renderHeatmap();
}

function changeHeatmapGrouping(grouping) {
    heatmapGrouping = grouping;
    loadHeatmapData();
}

function loadHeatmapData() {
    const container = document.getElementById('heatmapContainer');
    if (!container) return;

    container.innerHTML = '<div style="color:#6b7280;text-align:center;padding:40px;">⏳ Loading heatmap data...</div>';

    fetch(`/?action=heatmap_data&grouping=${ heatmapGrouping }`)
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                container.innerHTML = '<div style="color:#ef4444;text-align:center;padding:40px;">Error loading data</div>';
                return;
            }
            heatmapData = data.data;
            renderHeatmap();
        })
        .catch(err => {
            container.innerHTML = `<div style="color:#ef4444;text-align:center;padding:40px;">Error: ${err.message}</div>`;
        });
}

function getColorForValue(value, metric) {
    // Returns color based on metric type and value
    if (value === null || value === undefined) return '#374151';

    if (metric === 'pe') {
        // PE: < 10 green, 10-12 orange, > 12 red
        if (value < 10) {
            return 'rgb(34, 197, 94)';  // Green
        } else if (value <= 12) {
            return 'rgb(251, 146, 60)'; // Orange
        } else {
            return 'rgb(239, 68, 68)';  // Red
        }
    } else if (metric === 'pcf') {
        // P/CF: <= 8 green (excellent), 8-12 orange (correct), > 12 red (expensive)
        if (value <= 8) {
            return 'rgb(34, 197, 94)';  // Green - excellent
        } else if (value <= 12) {
            return 'rgb(251, 146, 60)'; // Orange - correct
        } else {
            return 'rgb(239, 68, 68)';  // Red - expensive
        }
    } else if (metric === 'score') {
        // Score: 0-4 red, 5-6 orange, 7-10 green
        if (value >= 7) {
            const intensity = Math.min((value - 7) / 3, 1);
            return `rgb(${34 - intensity * 10}, ${150 + intensity * 47}, ${70 + intensity * 24})`;
        } else if (value >= 5) {
            return 'rgb(251, 146, 60)'; // Orange
        } else {
            const intensity = Math.min((5 - value) / 5, 1);
            return `rgb(${180 + intensity * 59}, ${68 - intensity * 30}, ${68 - intensity * 30})`;
        }
    } else {
        // Performance metrics: positive = green, negative = red
        // Scale: -10% to +10%
        const normalized = Math.max(-1, Math.min(1, value / 10));
        if (normalized >= 0) {
            const intensity = normalized;
            return `rgb(${34 - intensity * 10}, ${100 + intensity * 97}, ${50 + intensity * 44})`;
        } else {
            const intensity = -normalized;
            return `rgb(${180 + intensity * 59}, ${68 - intensity * 30}, ${68 - intensity * 30})`;
        }
    }
}

function squarify(data, x, y, width, height) {
    // Squarified treemap algorithm
    if (!data.length) return [];

    const totalValue = data.reduce((sum, d) => sum + d.value, 0);
    if (totalValue === 0) return [];

    const results = [];
    let remaining = [...data];
    let currentX = x, currentY = y, currentW = width, currentH = height;

    while (remaining.length > 0) {
        const isHorizontal = currentW >= currentH;
        const side = isHorizontal ? currentH : currentW;

        let row = [];
        let rowValue = 0;
        let worstRatio = Infinity;

        for (let i = 0; i < remaining.length; i++) {
            const testRow = [...row, remaining[i]];
            const testValue = rowValue + remaining[i].value;
            const testRatio = getWorstRatio(testRow, testValue, side, totalValue, currentW * currentH);

            if (testRatio <= worstRatio) {
                row = testRow;
                rowValue = testValue;
                worstRatio = testRatio;
            } else {
                break;
            }
        }

        // Layout this row
        const rowArea = (rowValue / totalValue) * currentW * currentH;
        const rowLength = rowArea / side;

        let offset = 0;
        for (const item of row) {
            const itemArea = (item.value / totalValue) * currentW * currentH;
            const itemLength = itemArea / rowLength;

            if (isHorizontal) {
                results.push({
                    ...item,
                    x: currentX,
                    y: currentY + offset,
                    width: rowLength,
                    height: itemLength
                });
            } else {
                results.push({
                    ...item,
                    x: currentX + offset,
                    y: currentY,
                    width: itemLength,
                    height: rowLength
                });
            }
            offset += itemLength;
        }

        // Update remaining area
        remaining = remaining.slice(row.length);
        if (isHorizontal) {
            currentX += rowLength;
            currentW -= rowLength;
        } else {
            currentY += rowLength;
            currentH -= rowLength;
        }
    }

    return results;
}

function getWorstRatio(row, rowValue, side, totalValue, totalArea) {
    if (!row.length) return Infinity;
    const rowArea = (rowValue / totalValue) * totalArea;
    const rowLength = rowArea / side;

    let worst = 0;
    for (const item of row) {
        const itemArea = (item.value / totalValue) * totalArea;
        const itemLength = itemArea / rowLength;
        const ratio = Math.max(rowLength / itemLength, itemLength / rowLength);
        worst = Math.max(worst, ratio);
    }
    return worst;
}

function renderHeatmap() {
    const container = document.getElementById('heatmapContainer');
    if (!container || !heatmapData) return;

    const rect = container.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const padding = 4;
    const groupPadding = 20;

    container.innerHTML = '';

    const groups = heatmapData.groups;
    if (!groups || !groups.length) {
        container.innerHTML = '<div style="color:#6b7280;text-align:center;padding:40px;">No data available</div>';
        return;
    }

    // Calculate group rectangles
    const groupData = groups.map(g => ({ name: g.name, value: g.value, positions: g.positions }));
    const groupRects = squarify(groupData, padding, padding, width - padding * 2, height - padding * 2);

    for (const groupRect of groupRects) {
        const group = groups.find(g => g.name === groupRect.name);
        if (!group) continue;

        // Create group container
        const groupDiv = document.createElement('div');
        groupDiv.style.cssText = `
            position: absolute;
            left: ${groupRect.x}px;
            top: ${groupRect.y}px;
            width: ${groupRect.width}px;
            height: ${groupRect.height}px;
            border: 1px solid #374151;
            box-sizing: border-box;
            overflow: hidden;
        `;

        // Group header
        if (heatmapGrouping !== 'flat') {
            const header = document.createElement('div');
            header.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                background: rgba(15, 20, 25, 0.9);
                color: #9ca3af;
                font-size: 10px;
                padding: 2px 4px;
                text-transform: uppercase;
                z-index: 1;
                border-bottom: 1px solid #374151;
            `;
            header.textContent = `${groupRect.name} (${(group.weight ?? 0).toFixed(1)}%)`;
            groupDiv.appendChild(header);
        }

        // Calculate position rectangles within group
        const innerX = 0;
        const innerY = heatmapGrouping !== 'flat' ? 18 : 0;
        const innerW = groupRect.width - 2;
        const innerH = groupRect.height - (heatmapGrouping !== 'flat' ? 20 : 2);

        const posData = group.positions.map(p => ({ ...p }));
        const posRects = squarify(posData, innerX, innerY, innerW, innerH);

        for (const posRect of posRects) {
            const pos = group.positions.find(p => p.ticker === posRect.ticker);
            if (!pos) continue;

            const metricValue = pos[heatmapMetric];
            const bgColor = getColorForValue(metricValue, heatmapMetric);

            const posDiv = document.createElement('div');
            posDiv.className = 'heatmap-cell';
            posDiv.dataset.ticker = pos.ticker;
            posDiv.style.cssText = `
                position: absolute;
                left: ${posRect.x + 1}px;
                top: ${posRect.y + 1}px;
                width: ${Math.max(posRect.width - 2, 0)}px;
                height: ${Math.max(posRect.height - 2, 0)}px;
                background: ${ bgColor };
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                cursor: pointer;
                transition: transform 0.1s, box-shadow 0.1s;
                overflow: hidden;
            `;

            // Content based on cell size
            if (posRect.width > 60 && posRect.height > 40) {
                const safeValue = metricValue ?? 0;
                const displayValue = heatmapMetric === 'pe' ? (metricValue !== null ? metricValue : '-') :
                                     heatmapMetric === 'score' ? `${metricValue ?? 5}/10` :
                                     `${safeValue >= 0 ? '+' : ''}${safeValue.toFixed(1)}%`;
                posDiv.innerHTML = `
                    <div style="color:#fff;font-weight:bold;font-size:${posRect.width > 100 ? '13px' : '11px'};text-shadow:0 1px 2px rgba(0,0,0,0.5);">${pos.ticker}</div>
                    <div style="color:rgba(255,255,255,0.9);font-size:${posRect.width > 100 ? '12px' : '10px'};">${ displayValue }</div>
                    ${posRect.height > 55 ? `<div style="color:rgba(255,255,255,0.6);font-size:9px;">${(pos.weight ?? 0).toFixed(1)}%</div>` : ''}
                `;
            } else if (posRect.width > 35 && posRect.height > 25) {
                posDiv.innerHTML = `<div style="color:#fff;font-weight:bold;font-size:10px;text-shadow:0 1px 2px rgba(0,0,0,0.5);">${pos.ticker}</div>`;
            }

            // Hover events
            posDiv.addEventListener('mouseenter', (e) => showHeatmapTooltip(e, pos));
            posDiv.addEventListener('mouseleave', hideHeatmapTooltip);
            posDiv.addEventListener('mousemove', (e) => moveHeatmapTooltip(e));

            // Click to navigate
            posDiv.addEventListener('click', () => {
                window.location.href = `/detail?${pos.ticker}`;
            });

            groupDiv.appendChild(posDiv);
        }

        container.appendChild(groupDiv);
    }

    // Add hover style
    const style = document.createElement('style');
    style.textContent = `
        .heatmap-cell:hover {
            transform: scale(1.02);
            box-shadow: 0 0 12px rgba(255,255,255,0.3);
            z-index: 10;
        }
    `;
    container.appendChild(style);
}

function showHeatmapTooltip(e, pos) {
    const tooltip = document.getElementById('heatmapTooltip');
    if (!tooltip) return;

    const pe = pos.pe ?? null;
    const roe = pos.roe ?? null;
    const score = pos.score ?? 5;
    const pnl = pos.pnl_pct ?? 0;
    const change = pos.change_pct ?? 0;
    const weight = pos.weight ?? 0;

    const peColor = pe !== null ? (pe < 10 ? '#22c55e' : (pe < 17 ? '#ffd700' : '#ef4444')) : '#6b7280';
    const roeColor = roe !== null ? (roe > 15 ? '#22c55e' : (roe > 10 ? '#ffd700' : '#ef4444')) : '#6b7280';
    const scoreColor = score >= 7 ? '#22c55e' : (score >= 4 ? '#ffd700' : '#ef4444');
    const pnlColor = pnl >= 0 ? '#22c55e' : '#ef4444';

    tooltip.innerHTML = `
        <div style="font-weight:bold;color:#ffd700;margin-bottom:8px;">${pos.ticker} - ${pos.name}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;font-size:12px;">
            <div style="color:#6b7280;">Secteur:</div><div style="color:#9ca3af;">${pos.sector}</div>
            <div style="color:#6b7280;">Poids:</div><div style="color:#22d3ee;">${weight.toFixed(1)}%</div>
            <div style="color:#6b7280;">Valeur:</div><div style="color:#fff;">${formatMoney(pos.value)}</div>
            <div style="color:#6b7280;">P&L:</div><div style="color:${ pnlColor };">${pnl >= 0 ? '+' : ''}${pnl.toFixed(1)}%</div>
            <div style="color:#6b7280;">Jour:</div><div style="color:${change >= 0 ? '#22c55e' : '#ef4444'};">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</div>
            <div style="color:#6b7280;">PE:</div><div style="color:${ peColor };">${pe !== null ? pe : '-'}</div>
            <div style="color:#6b7280;">ROE:</div><div style="color:${ roeColor };">${roe !== null ? roe.toFixed(1) + '%' : '-'}</div>
            <div style="color:#6b7280;">Score:</div><div style="color:${ scoreColor };">${ score }/10</div>
        </div>
    `;

    tooltip.style.display = 'block';
    moveHeatmapTooltip(e);
}

function moveHeatmapTooltip(e) {
    const tooltip = document.getElementById('heatmapTooltip');
    if (!tooltip) return;

    let x = e.clientX + 15;
    let y = e.clientY + 15;

    // Keep tooltip on screen
    const rect = tooltip.getBoundingClientRect();
    if (x + rect.width > window.innerWidth - 10) {
        x = e.clientX - rect.width - 15;
    }
    if (y + rect.height > window.innerHeight - 10) {
        y = e.clientY - rect.height - 15;
    }

    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
}

function hideHeatmapTooltip() {
    const tooltip = document.getElementById('heatmapTooltip');
    if (tooltip) tooltip.style.display = 'none';
}

// Keyboard shortcut for F10
document.addEventListener('keydown', function(e) {
    if (e.key === 'F10') {
        e.preventDefault();
        toggleHeatmapPanel();
    }
});

// Keyboard shortcut for F11
document.addEventListener('keydown', function(e) {
    if (e.key === 'F11') {
        e.preventDefault();
        runPortfolioAdvisor();
    }
});