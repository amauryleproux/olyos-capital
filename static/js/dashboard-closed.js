function toggleClosedPositions() {
    const content = document.getElementById('closed-content');
    const toggle = document.getElementById('closed-toggle');
    if (content.style.display === 'none') {
        content.style.display = 'block';
        toggle.classList.add('open');
        loadClosedPositions();
    } else {
        content.style.display = 'none';
        toggle.classList.remove('open');
    }
}

function loadClosedPositions() {
    fetch('/?action=get_closed_positions')
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                console.error('Error loading closed positions:', data.error);
                return;
            }
            const positions = data.data || [];
            const tbody = document.getElementById('closed-body');
            const countEl = document.getElementById('closed-count');
            const pnlEl = document.getElementById('closed-total-pnl');

            countEl.textContent = positions.length;

            if (positions.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:#666;">No closed positions yet</td></tr>';
                pnlEl.textContent = '€0';
                return;
            }

            let totalPnl = 0;
            tbody.innerHTML = positions.map(p => {
                totalPnl += p.realized_pnl || 0;
                const pnlClass = p.realized_pnl >= 0 ? 'pos' : 'neg';
                const pnlSign = p.realized_pnl >= 0 ? '+' : '';
                const pnlPct = p.total_invested > 0 ? (p.realized_pnl / p.total_invested * 100).toFixed(1) : 0;
                return `<tr>
                    <td><a class="tk" href="/detail?${p.ticker}">${p.ticker}</a></td>
                    <td class="nm">${p.name || ''}</td>
                    <td style="text-align:right">€${p.total_invested.toLocaleString('fr-FR', {minimumFractionDigits: 0})}</td>
                    <td style="text-align:right">€${(p.total_invested + p.realized_pnl).toLocaleString('fr-FR', {minimumFractionDigits: 0})}</td>
                    <td style="text-align:right" class="${ pnlClass }">${ pnlSign }€${Math.abs(p.realized_pnl).toFixed(2)}</td>
                    <td style="text-align:right" class="${ pnlClass }">${ pnlSign }${ pnlPct }%</td>
                    <td style="text-align:right">${p.holding_days}d</td>
                    <td>${p.close_date || '-'}</td>
                </tr>`;
            }).join('');

            const totalSign = totalPnl >= 0 ? '+' : '';
            pnlEl.textContent = totalSign + '€' + Math.abs(totalPnl).toLocaleString('fr-FR', {minimumFractionDigits: 2});
            pnlEl.className = 'bb-closed-pnl ' + (totalPnl >= 0 ? 'positive' : 'negative');
        })
        .catch(err => {
            console.error('Error loading closed positions:', err);
        });
}

// Load P&L summary for KPIs
function loadPnLSummary() {
    fetch('/?action=get_pnl_summary')
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            const summary = data.data;

            // Update KPIs if elements exist
            const realizedEl = document.getElementById('kpi-realized-pnl');
            const unrealizedEl = document.getElementById('kpi-unrealized-pnl');
            const winRateEl = document.getElementById('kpi-win-rate');

            if (realizedEl) {
                const sign = summary.total_realized_pnl >= 0 ? '+' : '';
                realizedEl.textContent = sign + '€' + Math.abs(summary.total_realized_pnl).toFixed(0);
                realizedEl.style.color = summary.total_realized_pnl >= 0 ? '#00ff00' : '#ff3333';
            }
            if (unrealizedEl) {
                const sign = summary.total_unrealized_pnl >= 0 ? '+' : '';
                unrealizedEl.textContent = sign + '€' + Math.abs(summary.total_unrealized_pnl).toFixed(0);
                unrealizedEl.style.color = summary.total_unrealized_pnl >= 0 ? '#00ff00' : '#ff3333';
            }
            if (winRateEl) {
                winRateEl.textContent = summary.win_rate.toFixed(0) + '%';
            }

            // Update closed positions count
            const closedCount = document.getElementById('closed-count');
            if (closedCount) {
                closedCount.textContent = summary.closed_positions?.length || 0;
            }
        })
        .catch(err => console.error('Error loading P&L summary:', err));
}

// Load P&L summary on page load
setTimeout(loadPnLSummary, 500);