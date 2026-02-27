// ═══ BLOOMBERG LOADER ═══

let bbgLoadStartTime = 0;

let bbgLoadInterval = null;



function showBBGLoader(positions, nav, message) {

  const loader = document.getElementById('bbg-loader');

  bbgLoadStartTime = Date.now();



  document.getElementById('bbg-load-positions').textContent = positions || '—';

  document.getElementById('bbg-load-nav').textContent = nav || '—';

  document.getElementById('bbg-load-time').textContent = 'LOADING';

  document.getElementById('bbg-load-msg').textContent = message || 'Loading portfolio data...';



  loader.classList.add('active');



  // Update timer

  bbgLoadInterval = setInterval(() => {

    const elapsed = Math.round((Date.now() - bbgLoadStartTime) / 1000);

    document.getElementById('bbg-load-time').textContent = elapsed + 's';

  }, 100);

}



function updateBBGLoader(positions, nav, message) {

  if (positions != null) document.getElementById('bbg-load-positions').textContent = positions;

  if (nav != null) document.getElementById('bbg-load-nav').textContent = nav;

  if (message) document.getElementById('bbg-load-msg').textContent = message;

}



function hideBBGLoader() {

  const loader = document.getElementById('bbg-loader');

  loader.classList.remove('active');

  if (bbgLoadInterval) {

    clearInterval(bbgLoadInterval);

    bbgLoadInterval = null;

  }

}



// Show loader on page load, hide after content is ready

showBBGLoader(_D.activeCount, _D.tvFormatted + ' EUR', 'Loading portfolio data...');

setTimeout(() => {

  updateBBGLoader(_D.activeCount, _D.tvFormatted + ' EUR', 'Portfolio loaded successfully!');

  setTimeout(() => hideBBGLoader(), 500);

}, 800);



var scr=_D.screener;

var wl=_D.watchlistTickers;

function showTab(n){document.querySelectorAll('.bb-tab').forEach((t,i)=>t.classList.toggle('active',i===n));document.querySelectorAll('.fkey').forEach((f,i)=>{if(i<3)f.classList.toggle('active',i===n)});document.querySelectorAll('.tc').forEach((c,i)=>c.classList.toggle('active',i===n))}

function render(d){var tb=document.getElementById('stbl');tb.innerHTML='';d.sort((a,b)=>(b.score||0)-(a.score||0)).forEach((s,idx)=>{var sig=s.signal||'';var cls=sig==='ACHAT'?'sig-buy':sig==='AI BUY'?'sig-ai':sig==='CHER'?'sig-sell':sig==='WATCH'?'sig-watch':'sig-hold';var inW=wl.includes(s.ticker);var rank=s.ai_rank||(idx+1);var debtPct=s.debt_equity?(s.debt_equity<5?(s.debt_equity*100).toFixed(0):s.debt_equity.toFixed(0))+'%':'-';var roePct=s.roe?(s.roe<1?(s.roe*100).toFixed(0):s.roe.toFixed(0))+'%':'-';tb.innerHTML+='<tr><td style="color:#666">'+rank+'</td><td><a class="tk" href="/detail?'+s.ticker+'">'+s.ticker+'</a></td><td class="nm">'+s.name+'</td><td>'+s.country+'</td><td>'+s.sector+'</td><td class="r">'+(s.pe?s.pe.toFixed(1):'-')+'</td><td class="r">'+roePct+'</td><td class="r">'+debtPct+'</td><td class="r">'+(s.score||'-')+'</td><td class="c"><span class="sig '+cls+'">'+sig+'</span></td><td><button class="bb-btn" onclick="addW(\''+s.ticker+'\',\''+encodeURIComponent(s.name)+'\',\''+s.country+'\',\''+encodeURIComponent(s.sector)+'\')\"'+(inW?' disabled style="opacity:0.3"':'')+'>'+(inW?'ADDED':'+ WATCH')+'</button></td></tr>'})}

render(scr);

function flt(){var c=document.getElementById('fC').value,pe=parseFloat(document.getElementById('fP').value)||999,sig=document.getElementById('fS').value;render(scr.filter(s=>(!c||s.country===c)&&(!s.pe||s.pe<=pe)&&(!sig||s.signal===sig)))}

function addW(t,n,c,s){fetch('/?action=addwatch&ticker='+t+'&name='+n+'&country='+c+'&sector='+s).then(()=>location.reload())}

function rmW(t){fetch('/?action=rmwatch&ticker='+t).then(()=>location.reload())}

function runScreenerScan(){

    const scope = document.getElementById('screener-scope').value;

    const mode = document.getElementById('screener-mode').value;

    const modeText = mode === 'ai_optimal' ? 'AI Optimal (PE<=8, ROE>=12%, Top 18)' : 'Standard';

    if(confirm('Run ' + modeText + ' scan on ' + scope + ' universe? This may take a few minutes.')){

        location.href='/?screener=1&scope=' + scope + '&mode=' + mode;

    }

}

document.getElementById('screener-mode')?.addEventListener('change', function(){

    const banner = document.getElementById('ai-criteria-banner');

    if(this.value === 'ai_optimal'){

        banner.style.display = 'flex';

    } else {

        banner.style.display = 'none';

    }

});

// Sort Holdings table

(function(){

const table=document.getElementById('holdings-table');

if(!table)return;

const headers=table.querySelectorAll('th.sortable');

const tbody=document.getElementById('holdings-body');

let currentSort={col:-1,asc:true};

headers.forEach(th=>{

th.addEventListener('click',function(){

const col=parseInt(this.dataset.col);

const type=this.dataset.type;

const asc=currentSort.col===col?!currentSort.asc:true;

currentSort={col,asc};

headers.forEach(h=>h.classList.remove('asc','desc'));

this.classList.add(asc?'asc':'desc');

const rows=Array.from(tbody.querySelectorAll('tr'));

rows.sort((a,b)=>{

let aVal=a.cells[col].textContent.trim();

let bVal=b.cells[col].textContent.trim();

if(type==='number'){

aVal=parseFloat(aVal.replace(/[^0-9.-]/g,''))||0;

bVal=parseFloat(bVal.replace(/[^0-9.-]/g,''))||0;

return asc?aVal-bVal:bVal-aVal;

}else{

return asc?aVal.localeCompare(bVal):bVal.localeCompare(aVal);

}

});

rows.forEach(row=>tbody.appendChild(row));

});

});

})();

// NAV Chart

const navData = _D.navData;

let navPeriod = 365;



function setNavPeriod(days) {

    navPeriod = days;

    document.querySelectorAll('.bb-portfolio-chart .bb-chart-period button').forEach(b => b.classList.remove('active'));

    const btnId = days === 7 ? 'nav-1w' : days === 30 ? 'nav-1m' : days === 90 ? 'nav-3m' : 'nav-1y';

    document.getElementById(btnId).classList.add('active');

    drawNavChart();

}



function drawNavChart() {

    const canvas = document.getElementById('navChart');

    if (!canvas || !navData.length) return;

    

    const ctx = canvas.getContext('2d');

    const rect = canvas.parentElement.getBoundingClientRect();

    canvas.width = rect.width;

    canvas.height = rect.height;

    

    const data = navData.slice(-navPeriod);

    if (data.length < 2) {

        ctx.fillStyle = '#666';

        ctx.font = '12px JetBrains Mono';

        ctx.textAlign = 'center';

        ctx.fillText('Not enough data yet. Refresh daily to track performance.', canvas.width/2, canvas.height/2);

        return;

    }

    

    const navs = data.map(d => d.nav);

    const minNav = Math.min(...navs) * 0.99;

    const maxNav = Math.max(...navs) * 1.01;

    const navRange = maxNav - minNav || 1;

    

    const padding = { top: 15, right: 70, bottom: 25, left: 10 };

    const chartWidth = canvas.width - padding.left - padding.right;

    const chartHeight = canvas.height - padding.top - padding.bottom;

    

    ctx.fillStyle = '#050505';

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    

    // Grid

    ctx.strokeStyle = '#1a1a1a';

    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i++) {

        const y = padding.top + (chartHeight / 4) * i;

        ctx.beginPath();

        ctx.moveTo(padding.left, y);

        ctx.lineTo(canvas.width - padding.right, y);

        ctx.stroke();

        

        const nav = maxNav - (navRange / 4) * i;

        ctx.fillStyle = '#666';

        ctx.font = '10px JetBrains Mono';

        ctx.textAlign = 'left';

        ctx.fillText(nav.toFixed(0), canvas.width - padding.right + 5, y + 4);

    }

    

    // Cost basis line

    const avgCost = data[0].cost;

    if (avgCost > minNav && avgCost < maxNav) {

        const costY = padding.top + ((maxNav - avgCost) / navRange) * chartHeight;

        ctx.strokeStyle = '#ff9500';

        ctx.setLineDash([3, 3]);

        ctx.beginPath();

        ctx.moveTo(padding.left, costY);

        ctx.lineTo(canvas.width - padding.right, costY);

        ctx.stroke();

        ctx.setLineDash([]);

        ctx.fillStyle = '#ff9500';

        ctx.font = '9px JetBrains Mono';

        ctx.fillText('COST', canvas.width - padding.right + 5, costY - 5);

    }

    

    const isPositive = navs[navs.length - 1] >= navs[0];

    const lineColor = isPositive ? '#00ff00' : '#ff3b30';

    const fillColor = isPositive ? 'rgba(0, 255, 0, 0.15)' : 'rgba(255, 59, 48, 0.15)';

    

    // Area fill

    ctx.beginPath();

    ctx.moveTo(padding.left, padding.top + chartHeight);

    data.forEach((d, i) => {

        const x = padding.left + (i / (data.length - 1)) * chartWidth;

        const y = padding.top + ((maxNav - d.nav) / navRange) * chartHeight;

        ctx.lineTo(x, y);

    });

    ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight);

    ctx.closePath();

    ctx.fillStyle = fillColor;

    ctx.fill();

    

    // Line

    ctx.beginPath();

    ctx.strokeStyle = lineColor;

    ctx.lineWidth = 2;

    data.forEach((d, i) => {

        const x = padding.left + (i / (data.length - 1)) * chartWidth;

        const y = padding.top + ((maxNav - d.nav) / navRange) * chartHeight;

        if (i === 0) ctx.moveTo(x, y);

        else ctx.lineTo(x, y);

    });

    ctx.stroke();

    

    // Current NAV

    const lastNav = navs[navs.length - 1];

    const lastY = padding.top + ((maxNav - lastNav) / navRange) * chartHeight;

    ctx.fillStyle = lineColor;

    ctx.font = 'bold 11px JetBrains Mono';

    ctx.fillText(lastNav.toFixed(0), canvas.width - padding.right + 5, lastY + 4);

    

    // Date labels

    ctx.fillStyle = '#666';

    ctx.font = '9px JetBrains Mono';

    ctx.textAlign = 'center';

    const labelCount = Math.min(5, data.length);

    for (let i = 0; i < labelCount; i++) {

        const idx = Math.floor((i / (labelCount - 1)) * (data.length - 1));

        const x = padding.left + (idx / (data.length - 1)) * chartWidth;

        const date = new Date(data[idx].date);

        const label = date.toLocaleDateString('fr-FR', { month: 'short', day: 'numeric' });

        ctx.fillText(label, x, canvas.height - 8);

    }

}



setTimeout(drawNavChart, 100);

window.addEventListener('resize', drawNavChart);



// ============= BACKTEST FUNCTIONS =============

let backtestResults = null;



// ============= CACHE FUNCTIONS =============

function loadCacheStats() {

    fetch('/?action=cache_stats')

        .then(r => r.json())

        .then(stats => {

            document.getElementById('cache-stats').innerHTML = 

                `<span>${stats.fundamentals}</span> fundamentals | ` +

                `<span>${stats.prices}</span> price series | ` +

                `<span>${stats.total_size_mb} MB</span> total`;

        })

        .catch(() => {

            document.getElementById('cache-stats').innerHTML = 'Unable to load cache stats';

        });

}



function downloadAllData(scope) {

    const btn = document.getElementById('dl-' + scope + '-btn');

    const originalText = btn.innerHTML;

    btn.disabled = true;

    btn.innerHTML = 'â³ Downloading...';

    

    fetch('/?action=download_data&scope=' + scope, {method: 'POST'})

        .then(r => r.json())

        .then(result => {

            btn.disabled = false;

            btn.innerHTML = originalText;

            

            if (result.error) {

                alert('Error: ' + result.error);

            } else {

                alert(`Download complete!\nâœ… Success: ${result.success}\nâŒ Errors: ${result.errors}\nTotal: ${result.total} tickers`);

                loadCacheStats();

            }

        })

        .catch(err => {

            btn.disabled = false;

            btn.innerHTML = originalText;

            alert('Error: ' + err);

        });

}



function clearCache() {

    if (!confirm('Are you sure you want to delete all cached data? You will need to re-download it.')) return;

    

    fetch('/?action=clear_cache', {method: 'POST'})

        .then(r => r.json())

        .then(result => {

            alert(result.message || 'Cache cleared');

            loadCacheStats();

        })

        .catch(err => alert('Error: ' + err));

}



// Load cache stats on page load

setTimeout(loadCacheStats, 500);

// ============== ALERTS FUNCTIONS ==============

function loadAlerts() {
    fetch('/?action=get_alerts')
        .then(r => r.json())
        .then(data => {
            displayAlerts(data.alerts || []);
        })
        .catch(err => {
            console.error('Error loading alerts:', err);
        });
}

function checkAlerts() {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '⏳ Checking...';

    fetch('/?action=check_alerts')
        .then(r => r.json())
        .then(data => {
            displayAlerts(data.alerts || []);
            btn.disabled = false;
            btn.textContent = '🔄 REFRESH';
        })
        .catch(err => {
            console.error('Error checking alerts:', err);
            btn.disabled = false;
            btn.textContent = '🔄 REFRESH';
        });
}

function displayAlerts(alerts) {
    const panel = document.getElementById('alerts-panel');
    const list = document.getElementById('alerts-list');
    const count = document.getElementById('alerts-count');
    const icon = document.getElementById('alerts-icon');

    if (!alerts || alerts.length === 0) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';
    count.textContent = alerts.length;
    icon.classList.add('active');

    list.innerHTML = alerts.map(a => {
        const typeClass = a.alert_type.toLowerCase().replace('_', '-');
        const alertId = `alert-${a.ticker}-${a.alert_type}`;
        return `
            <div class="bb-alert-item ${ typeClass }" id="${ alertId }">
                <span class="bb-alert-ticker">${a.ticker}</span>
                <span class="bb-alert-name">${a.name}</span>
                <span class="bb-alert-message">${a.message}</span>
                <div class="bb-alert-actions">
                    <button class="bb-alert-btn" onclick="window.location.href='/detail?${a.ticker}'">DETAIL</button>
                    <button class="bb-alert-btn dismiss" onclick="dismissAlert('${a.ticker}', '${a.alert_type}', this)">✕</button>
                </div>
            </div>
        `;
    }).join('');
}

function dismissAlert(ticker, alertType, btn) {
    // Immediately hide the alert for instant feedback
    const alertEl = document.getElementById(`alert-${ ticker }-${ alertType }`);
    if (alertEl) {
        alertEl.style.opacity = '0.3';
        alertEl.style.pointerEvents = 'none';
    }
    if (btn) btn.textContent = '...';

    fetch(`/?action=dismiss_alert&ticker=${ ticker }&alert_type=${ alertType }`)
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                // Remove element from DOM
                if (alertEl) alertEl.remove();
                // Update alert count
                const remaining = document.querySelectorAll('.bb-alert-item').length;
                const count = document.getElementById('alerts-count');
                if (count) count.textContent = remaining;
                if (remaining === 0) {
                    document.getElementById('alerts-panel').style.display = 'none';
                    document.getElementById('alerts-icon').classList.remove('active');
                }
            } else {
                // Restore if failed
                if (alertEl) {
                    alertEl.style.opacity = '1';
                    alertEl.style.pointerEvents = 'auto';
                }
                if (btn) btn.textContent = '✕';
            }
        })
        .catch(err => {
            console.error('Error dismissing alert:', err);
            // Restore on error
            if (alertEl) {
                alertEl.style.opacity = '1';
                alertEl.style.pointerEvents = 'auto';
            }
            if (btn) btn.textContent = '✕';
        });
}

// Load alerts on page load (delayed to not block initial render)
setTimeout(loadAlerts, 1000);

// ============== BENCHMARK COMPARISON ==============

let currentBenchmark = 'CACMS';
let currentBenchPeriod = '1Y';
let benchmarkChart = null;

function setBenchmark(benchmark) {
    currentBenchmark = benchmark;
    document.querySelectorAll('.bb-bench-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('bench-' + benchmark).classList.add('active');
    loadBenchmarkData();
}

function setBenchPeriod(period) {
    currentBenchPeriod = period;
    document.querySelectorAll('.bb-benchmark-period button').forEach(b => b.classList.remove('active'));
    document.getElementById('bench-' + period.toLowerCase()).classList.add('active');
    loadBenchmarkData();
}

function loadBenchmarkData() {
    fetch(`/?action=benchmark_compare&benchmark=${ currentBenchmark }&period=${ currentBenchPeriod }`)
        .then(r => {
            if (!r.ok) {
                console.error('Benchmark HTTP error:', r.status, r.statusText);
            }
            return r.json();
        })
        .then(data => {
            if (data.error) {
                console.error('Benchmark error:', data.error);
                return;
            }
            console.log('Benchmark data loaded:', {
                portfolio: (data.portfolio || []).length + ' pts',
                benchmark: (data.benchmark || []).length + ' pts'
            });
            displayBenchmarkChart(data);
            displayBenchmarkMetrics(data.metrics);
        })
        .catch(err => console.error('Error loading benchmark:', err));
}

function displayBenchmarkChart(data) {
    const ctx = document.getElementById('benchmarkChart');
    if (!ctx) return;

    const portfolio = data.portfolio || [];
    const benchmark = data.benchmark || [];

    if (portfolio.length === 0 && benchmark.length === 0) {
        return;
    }

    // Align data by date
    const portfolioMap = {};
    const benchmarkMap = {};
    portfolio.forEach(p => portfolioMap[p.date] = p.close);
    benchmark.forEach(b => benchmarkMap[b.date] = b.close);

    const allDates = [...new Set([...Object.keys(portfolioMap), ...Object.keys(benchmarkMap)])].sort();

    const labels = allDates;
    const portfolioData = allDates.map(d => portfolioMap[d] || null);
    const benchmarkData = allDates.map(d => benchmarkMap[d] || null);

    if (benchmarkChart) {
        benchmarkChart.destroy();
    }

    benchmarkChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Portfolio',
                    data: portfolioData,
                    borderColor: '#ff9500',
                    backgroundColor: 'rgba(255,149,0,0.1)',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.1
                },
                {
                    label: data.benchmark_info?.name || 'Benchmark',
                    data: benchmarkData,
                    borderColor: '#666',
                    backgroundColor: 'rgba(102,102,102,0.1)',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.1,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#888',
                        font: { size: 10 },
                        boxWidth: 15
                    }
                },
                tooltip: {
                    backgroundColor: '#1a1a1a',
                    borderColor: '#333',
                    borderWidth: 1,
                    titleColor: '#ff9500',
                    bodyColor: '#fff',
                    callbacks: {
                        label: function(ctx) {
                            return ctx.dataset.label + ': ' + (ctx.raw ? ctx.raw.toFixed(1) : '--');
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: { color: '#1a1a1a' },
                    ticks: {
                        color: '#666',
                        font: { size: 9 },
                        maxTicksLimit: 8,
                        callback: function(val, i) {
                            const label = this.getLabelForValue(val);
                            return label ? label.slice(5) : ''; // Show MM-DD
                        }
                    }
                },
                y: {
                    display: true,
                    grid: { color: '#1a1a1a' },
                    ticks: {
                        color: '#666',
                        font: { size: 9 },
                        callback: v => v.toFixed(0)
                    },
                    suggestedMin: 80,
                    suggestedMax: 120
                }
            }
        }
    });
}

function displayBenchmarkMetrics(metrics) {
    if (!metrics) return;

    // Alpha
    const alphaEl = document.getElementById('alpha-value');
    const alpha = metrics.alpha || 0;
    alphaEl.textContent = (alpha >= 0 ? '+' : '') + alpha.toFixed(1) + '%';
    alphaEl.className = 'bb-alpha-value ' + (alpha >= 0 ? '' : 'negative');

    // Portfolio return
    const portfolioEl = document.getElementById('metric-portfolio');
    const pRet = metrics.portfolio_return || 0;
    portfolioEl.textContent = (pRet >= 0 ? '+' : '') + pRet.toFixed(1) + '%';
    portfolioEl.className = 'bb-bench-metric-value ' + (pRet >= 0 ? 'pos' : 'neg');

    // Benchmark return
    const benchEl = document.getElementById('metric-benchmark');
    const bRet = metrics.benchmark_return || 0;
    benchEl.textContent = (bRet >= 0 ? '+' : '') + bRet.toFixed(1) + '%';
    benchEl.className = 'bb-bench-metric-value ' + (bRet >= 0 ? 'pos' : 'neg');

    // Beta
    document.getElementById('metric-beta').textContent = (metrics.beta || 0).toFixed(2);

    // Sharpe
    const sharpe = metrics.sharpe_ratio || 0;
    const sharpeEl = document.getElementById('metric-sharpe');
    sharpeEl.textContent = sharpe.toFixed(2);
    sharpeEl.className = 'bb-bench-metric-value ' + (sharpe >= 1 ? 'pos' : sharpe < 0 ? 'neg' : '');

    // Max Drawdown
    const maxDD = metrics.portfolio_max_dd || 0;
    const maxDDEl = document.getElementById('metric-maxdd');
    maxDDEl.textContent = '-' + Math.abs(maxDD).toFixed(1) + '%';
    maxDDEl.className = 'bb-bench-metric-value neg';

    // Tracking Error
    document.getElementById('metric-tracking').textContent = (metrics.tracking_error || 0).toFixed(1) + '%';

    // Update top KPIs bar
    const kpiAlpha = document.getElementById('kpi-alpha');
    if (kpiAlpha) {
        kpiAlpha.textContent = (alpha >= 0 ? '+' : '') + alpha.toFixed(1) + '%';
        kpiAlpha.style.color = alpha >= 0 ? '#00ff00' : '#ff3333';
    }

    const kpiBeta = document.getElementById('kpi-beta');
    if (kpiBeta) {
        kpiBeta.textContent = (metrics.beta || 0).toFixed(2);
    }

    const kpiSharpe = document.getElementById('kpi-sharpe');
    if (kpiSharpe) {
        kpiSharpe.textContent = sharpe.toFixed(2);
        kpiSharpe.style.color = sharpe >= 1 ? '#00ff00' : sharpe < 0 ? '#ff3333' : '#fff';
    }
}

// Load benchmark data on page load
setTimeout(loadBenchmarkData, 1500);

// ============== DIVIDENDS CALENDAR ==============

let currentDivPeriod = 3;

function setDivPeriod(months) {
    currentDivPeriod = months;
    document.querySelectorAll('.bb-div-period').forEach(b => b.classList.remove('active'));
    document.getElementById('div-' + months + 'm').classList.add('active');
    loadDividendData();
}

function loadDividendData() {
    // Load income projection
    fetch('/?action=dividends_income')
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                console.error('Dividend income error:', data.error);
                return;
            }
            displayDividendSummary(data);
            displayDividendBreakdown(data.breakdown || []);
        })
        .catch(err => console.error('Error loading dividend income:', err));

    // Load calendar
    fetch(`/?action=dividends_calendar&months=${ currentDivPeriod }`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                console.error('Dividend calendar error:', data.error);
                return;
            }
            displayUpcomingDividends(data.upcoming || []);
        })
        .catch(err => console.error('Error loading dividend calendar:', err));
}

function displayDividendSummary(data) {
    const annualEl = document.getElementById('div-annual-income');
    const monthlyEl = document.getElementById('div-monthly');
    const yieldEl = document.getElementById('div-yield');
    const payersEl = document.getElementById('div-payers');

    if (annualEl) {
        annualEl.textContent = '€' + (data.total_annual_income || 0).toLocaleString('fr-FR', {minimumFractionDigits: 0});
    }
    if (monthlyEl) {
        monthlyEl.textContent = '€' + (data.monthly_average || 0).toLocaleString('fr-FR', {minimumFractionDigits: 0});
    }
    if (payersEl) {
        payersEl.textContent = (data.positions_with_dividends || 0) + '/' + (data.total_positions || 0);
    }

    // Calculate portfolio yield (needs total portfolio value)
    // For now just show number of payers
}

function displayUpcomingDividends(upcoming) {
    const listEl = document.getElementById('div-upcoming-list');
    if (!listEl) return;

    if (!upcoming || upcoming.length === 0) {
        listEl.innerHTML = '<div class="bb-div-empty">No upcoming dividends in the next ' + currentDivPeriod + ' months</div>';
        return;
    }

    listEl.innerHTML = upcoming.map(div => `
        <div class="bb-div-item upcoming">
            <div class="bb-div-item-info">
                <span class="bb-div-item-ticker">${div.ticker}</span>
                <span class="bb-div-item-name">${div.name || ''}</span>
            </div>
            <div class="bb-div-item-details">
                <span class="bb-div-item-date">${formatDivDate(div.ex_date)}</span>
                <span class="bb-div-item-amount">€${div.expected_income.toFixed(2)}</span>
            </div>
        </div>
    `).join('');
}

function displayDividendBreakdown(breakdown) {
    const listEl = document.getElementById('div-breakdown-list');
    if (!listEl) return;

    if (!breakdown || breakdown.length === 0) {
        listEl.innerHTML = '<div class="bb-div-empty">No dividend data available</div>';
        return;
    }

    // Show top 6 contributors
    const top = breakdown.slice(0, 6);
    listEl.innerHTML = top.map(item => `
        <div class="bb-div-breakdown-item">
            <div>
                <span class="bb-div-breakdown-ticker">${item.ticker}</span>
                <span class="bb-div-breakdown-yield">${item.dividend_yield.toFixed(1)}%</span>
            </div>
            <span class="bb-div-breakdown-income">€${item.annual_income.toFixed(0)}/yr</span>
        </div>
    `).join('');
}

function formatDivDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((d - now) / (1000 * 60 * 60 * 24));

    const formatted = d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });

    if (diffDays <= 7) {
        return formatted + ' (' + diffDays + 'j)';
    }
    return formatted;
}

// Load dividend data on page load
setTimeout(loadDividendData, 2000);

function setScope(scope) {

    document.querySelectorAll('.bb-scope-btn').forEach(b => b.classList.remove('active'));

    document.getElementById('scope-' + scope).classList.add('active');

    document.getElementById('bt-scope').value = scope;

    

    const customField = document.getElementById('custom-universe-field');

    const infoDiv = document.getElementById('scope-info');

    

    if (scope === 'france') {

        customField.style.display = 'none';

        infoDiv.innerHTML = '<span style="color:#00ff00">[FR] France:</span> Will scan ~200 small/mid cap stocks on Euronext Paris';

    } else if (scope === 'europe') {

        customField.style.display = 'none';

        infoDiv.innerHTML = '<span style="color:#00bfff">[EU] Europe:</span> Will scan ~500+ stocks across major European exchanges (PA, AS, BR, MI, MC, XETRA, LSE, SW)';

    } else {

        customField.style.display = 'block';

        infoDiv.innerHTML = '<span style="color:#ff9500">âœï¸ Custom:</span> Enter specific tickers to test';

    }

}



function runBacktest() {

    const btn = document.getElementById('bt-run-btn');

    btn.disabled = true;

    btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px"></div> Loading data & running simulation...';

    

    const scope = document.getElementById('bt-scope').value;

    const customUniverse = document.getElementById('bt-universe').value;

    

    const params = {

        start_date: document.getElementById('bt-start').value,

        end_date: document.getElementById('bt-end').value,

        rebalance_freq: document.getElementById('bt-rebalance').value,

        pe_max: document.getElementById('bt-pe-max').value,

        roe_min: document.getElementById('bt-roe-min').value,

        pe_sell: document.getElementById('bt-pe-sell').value,

        roe_min_hold: document.getElementById('bt-roe-hold').value,

        debt_equity_max: document.getElementById('bt-debt-max').value,

        max_positions: document.getElementById('bt-max-pos').value,

        initial_capital: document.getElementById('bt-capital').value,

        benchmark: document.getElementById('bt-benchmark').value,

        universe_scope: scope,

        universe: scope === 'custom' ? customUniverse : ''

    };

    

    fetch('/?action=run_backtest', {

        method: 'POST',

        headers: {'Content-Type': 'application/json'},

        body: JSON.stringify(params)

    })

    .then(r => r.json())

    .then(data => {

        btn.disabled = false;

        btn.innerHTML = '<span>â–¶ RUN BACKTEST</span>';

        

        if (data.error) {

            alert('Error: ' + data.error);

            return;

        }

        

        backtestResults = data;

        displayBacktestResults(data);

    })

    .catch(err => {

        btn.disabled = false;

        btn.innerHTML = '<span>â–¶ RUN BACKTEST</span>';

        alert('Error: ' + err);

    });

}



function displayBacktestResults(data) {

    document.getElementById('bt-results').style.display = 'block';

    

    const m = data.metrics || {};

    const params = data.params || {};

    

    // Period display

    document.getElementById('bt-period-display').innerHTML = 

        `${params.start_date} â†’ ${params.end_date} | ${data.equity_curve?.length || 0} rebalancing periods`;

    

    // Metrics

    const metricsHtml = `

        <div class="bb-metric-card highlight">

            <span class="bb-metric-card-label">Total Return</span>

            <span class="bb-metric-card-value ${m.total_return >= 0 ? 'pos' : 'neg'}">${m.total_return?.toFixed(1) || 0}%</span>

            <span class="bb-metric-card-sub">vs Benchmark: ${m.benchmark_return?.toFixed(1) || 0}%</span>

        </div>

        <div class="bb-metric-card">

            <span class="bb-metric-card-label">CAGR</span>

            <span class="bb-metric-card-value ${m.cagr >= 0 ? 'pos' : 'neg'}">${m.cagr?.toFixed(2) || 0}%</span>

            <span class="bb-metric-card-sub">Annualized</span>

        </div>

        <div class="bb-metric-card">

            <span class="bb-metric-card-label">Max Drawdown</span>

            <span class="bb-metric-card-value neg">-${m.max_drawdown?.toFixed(1) || 0}%</span>

        </div>

        <div class="bb-metric-card">

            <span class="bb-metric-card-label">Sharpe Ratio</span>

            <span class="bb-metric-card-value">${m.sharpe?.toFixed(2) || 0}</span>

        </div>

        <div class="bb-metric-card">

            <span class="bb-metric-card-label">Win Rate</span>

            <span class="bb-metric-card-value">${m.win_rate?.toFixed(0) || 0}%</span>

            <span class="bb-metric-card-sub">${m.total_trades || 0} trades</span>

        </div>

        <div class="bb-metric-card highlight">

            <span class="bb-metric-card-label">Alpha</span>

            <span class="bb-metric-card-value ${m.alpha >= 0 ? 'pos' : 'neg'}">${m.alpha >= 0 ? '+' : ''}${m.alpha?.toFixed(1) || 0}%</span>

            <span class="bb-metric-card-sub">vs Benchmark</span>

        </div>

    `;

    document.getElementById('bt-metrics').innerHTML = metricsHtml;

    

    // Draw equity curve

    setTimeout(() => drawEquityCurve(data), 100);

    

    // Draw yearly returns

    setTimeout(() => drawYearlyReturns(data.yearly_returns || []), 100);

    

    // Trades table

    const trades = data.trades || [];

    let tradesHtml = '';

    trades.slice(-50).reverse().forEach(t => {

        const pnlClass = t.pnl_pct > 0 ? 'pos' : (t.pnl_pct < 0 ? 'neg' : '');

        const actionClass = t.action === 'BUY' ? 'sig-achat' : 'sig-ecarter';

        tradesHtml += `<tr>

            <td>${t.date}</td>

            <td><span class="sig ${ actionClass }">${t.action}</span></td>

            <td>${t.ticker}</td>

            <td class="r">${t.shares}</td>

            <td class="r">${t.price?.toFixed(2)}</td>

            <td class="r">${t.value?.toFixed(0)}</td>

            <td class="r ${ pnlClass }">${t.pnl_pct ? (t.pnl_pct > 0 ? '+' : '') + t.pnl_pct.toFixed(1) + '%' : '-'}</td>

        </tr>`;

    });

    document.getElementById('bt-trades-body').innerHTML = tradesHtml || '<tr><td colspan="7" style="text-align:center;color:#666">No trades</td></tr>';

    

    // Errors

    if (data.errors && data.errors.length > 0) {

        document.getElementById('bt-errors').style.display = 'block';

        document.getElementById('bt-errors-list').innerHTML = data.errors.map(e => `<li>${ e }</li>`).join('');

    } else {

        document.getElementById('bt-errors').style.display = 'none';

    }

}



function drawEquityCurve(data) {

    const canvas = document.getElementById('btChart');

    if (!canvas) return;

    

    const ctx = canvas.getContext('2d');

    const rect = canvas.parentElement.getBoundingClientRect();

    canvas.width = rect.width;

    canvas.height = rect.height;

    

    const equity = data.equity_curve || [];

    const benchmark = data.benchmark_curve || [];

    const initialCapital = data.params?.initial_capital || 100000;

    

    if (equity.length < 2) return;

    

    // Calculate P&L (portfolio value - initial capital)

    const pnlData = equity.map(e => ({

        date: e.date, 

        value: e.value,

        pnl: e.value - initialCapital

    }));

    

    // Normalize benchmark to same scale (P&L based on initial capital)

    let benchPnl = [];

    if (benchmark.length >= 2) {

        const bStart = benchmark[0].price;

        benchPnl = benchmark.map(b => ({

            date: b.date, 

            pnl: ((b.price / bStart) - 1) * initialCapital

        }));

    }

    

    // Find min/max P&L for scale

    const allPnl = [...pnlData.map(e => e.pnl), ...benchPnl.map(b => b.pnl)];

    const minPnl = Math.min(...allPnl, 0) * 1.1;  // Include 0 and add margin

    const maxPnl = Math.max(...allPnl) * 1.1;

    const range = maxPnl - minPnl || 1;

    

    const padding = {top: 20, right: 80, bottom: 30, left: 10};

    const w = canvas.width - padding.left - padding.right;

    const h = canvas.height - padding.top - padding.bottom;

    

    // Clear

    ctx.fillStyle = '#050505';

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    

    // Zero line (breakeven)

    const zeroY = padding.top + ((maxPnl - 0) / range) * h;

    ctx.strokeStyle = '#333';

    ctx.lineWidth = 1;

    ctx.setLineDash([5, 3]);

    ctx.beginPath();

    ctx.moveTo(padding.left, zeroY);

    ctx.lineTo(canvas.width - padding.right, zeroY);

    ctx.stroke();

    ctx.setLineDash([]);

    ctx.fillStyle = '#666';

    ctx.font = '9px JetBrains Mono';

    ctx.textAlign = 'left';

    ctx.fillText('BREAKEVEN', padding.left + 5, zeroY - 5);

    

    // Grid and Y-axis labels (P&L in euros)

    ctx.strokeStyle = '#1a1a1a';

    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i++) {

        const y = padding.top + (h / 4) * i;

        ctx.beginPath();

        ctx.moveTo(padding.left, y);

        ctx.lineTo(canvas.width - padding.right, y);

        ctx.stroke();

        

        const pnlVal = maxPnl - (range / 4) * i;

        const pnlStr = pnlVal >= 0 ? '+' + formatEur(pnlVal) : formatEur(pnlVal);

        ctx.fillStyle = pnlVal >= 0 ? '#00ff00' : '#ff3b30';

        ctx.font = '10px JetBrains Mono';

        ctx.textAlign = 'left';

        ctx.fillText(pnlStr, canvas.width - padding.right + 5, y + 4);

    }

    

    // Benchmark P&L line (orange)

    if (benchPnl.length > 1) {

        ctx.beginPath();

        ctx.strokeStyle = '#ff9500';

        ctx.lineWidth = 1.5;

        benchPnl.forEach((b, i) => {

            const x = padding.left + (i / (benchPnl.length - 1)) * w;

            const y = padding.top + ((maxPnl - b.pnl) / range) * h;

            if (i === 0) ctx.moveTo(x, y);

            else ctx.lineTo(x, y);

        });

        ctx.stroke();

    }

    

    // Strategy P&L line (green/red based on final result)

    const finalPnl = pnlData[pnlData.length - 1].pnl;

    const strategyColor = finalPnl >= 0 ? '#00ff00' : '#ff3b30';

    

    // Fill area under curve

    ctx.beginPath();

    ctx.moveTo(padding.left, zeroY);

    pnlData.forEach((e, i) => {

        const x = padding.left + (i / (pnlData.length - 1)) * w;

        const y = padding.top + ((maxPnl - e.pnl) / range) * h;

        ctx.lineTo(x, y);

    });

    ctx.lineTo(padding.left + w, zeroY);

    ctx.closePath();

    ctx.fillStyle = finalPnl >= 0 ? 'rgba(0, 255, 0, 0.1)' : 'rgba(255, 59, 48, 0.1)';

    ctx.fill();

    

    // Strategy line

    ctx.beginPath();

    ctx.strokeStyle = strategyColor;

    ctx.lineWidth = 2;

    pnlData.forEach((e, i) => {

        const x = padding.left + (i / (pnlData.length - 1)) * w;

        const y = padding.top + ((maxPnl - e.pnl) / range) * h;

        if (i === 0) ctx.moveTo(x, y);

        else ctx.lineTo(x, y);

    });

    ctx.stroke();

    

    // Final P&L label

    const lastX = padding.left + w;

    const lastY = padding.top + ((maxPnl - finalPnl) / range) * h;

    ctx.fillStyle = strategyColor;

    ctx.font = 'bold 11px JetBrains Mono';

    ctx.textAlign = 'left';

    const finalStr = (finalPnl >= 0 ? '+' : '') + formatEur(finalPnl);

    ctx.fillText(finalStr, lastX + 5, lastY);

    

    // Date labels (X-axis)

    ctx.fillStyle = '#666';

    ctx.font = '9px JetBrains Mono';

    ctx.textAlign = 'center';

    const labelCount = Math.min(6, pnlData.length);

    for (let i = 0; i < labelCount; i++) {

        const idx = Math.floor((i / (labelCount - 1)) * (pnlData.length - 1));

        const x = padding.left + (idx / (pnlData.length - 1)) * w;

        ctx.fillText(pnlData[idx].date.substring(0, 7), x, canvas.height - 8);

    }

}



function formatEur(val) {

    if (Math.abs(val) >= 1000000) return (val / 1000000).toFixed(1) + 'Mâ‚¬';

    if (Math.abs(val) >= 1000) return (val / 1000).toFixed(0) + 'Kâ‚¬';

    return val.toFixed(0) + 'â‚¬';

}



function drawYearlyReturns(yearly) {

    const canvas = document.getElementById('btYearlyChart');

    if (!canvas || !yearly.length) return;

    

    const ctx = canvas.getContext('2d');

    const rect = canvas.parentElement.getBoundingClientRect();

    canvas.width = rect.width;

    canvas.height = rect.height;

    

    const padding = {top: 20, right: 20, bottom: 30, left: 50};

    const w = canvas.width - padding.left - padding.right;

    const h = canvas.height - padding.top - padding.bottom;

    

    const maxRet = Math.max(...yearly.map(y => Math.abs(y.return)), 10);

    

    ctx.fillStyle = '#050505';

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    

    // Zero line

    const zeroY = padding.top + h / 2;

    ctx.strokeStyle = '#333';

    ctx.beginPath();

    ctx.moveTo(padding.left, zeroY);

    ctx.lineTo(canvas.width - padding.right, zeroY);

    ctx.stroke();

    

    const barWidth = w / yearly.length * 0.7;

    const gap = w / yearly.length * 0.3;

    

    yearly.forEach((y, i) => {

        const x = padding.left + i * (barWidth + gap) + gap / 2;

        const barH = (y.return / maxRet) * (h / 2);

        const barY = y.return >= 0 ? zeroY - barH : zeroY;

        

        ctx.fillStyle = y.return >= 0 ? '#00ff00' : '#ff3b30';

        ctx.fillRect(x, y.return >= 0 ? barY : zeroY, barWidth, Math.abs(barH));

        

        // Year label

        ctx.fillStyle = '#888';

        ctx.font = '9px JetBrains Mono';

        ctx.textAlign = 'center';

        ctx.fillText(y.year, x + barWidth / 2, canvas.height - 8);

        

        // Value label

        ctx.fillStyle = y.return >= 0 ? '#00ff00' : '#ff3b30';

        ctx.fillText((y.return >= 0 ? '+' : '') + y.return.toFixed(0) + '%', 

            x + barWidth / 2, y.return >= 0 ? barY - 5 : zeroY + Math.abs(barH) + 12);

    });

}



function resetBacktest() {

    document.getElementById('bt-results').style.display = 'none';

    document.getElementById('ai-results').style.display = 'none';

    document.getElementById('bt-start').value = '2014-01-01';

    document.getElementById('bt-end').value = new Date().toISOString().split('T')[0];

    document.getElementById('bt-pe-max').value = '12';

    document.getElementById('bt-roe-min').value = '10';

    document.getElementById('bt-debt-max').value = '100';

    document.getElementById('bt-max-pos').value = '20';

    document.getElementById('bt-capital').value = '100000';

}



// ============= AI OPTIMIZER =============

let aiOptimalParams = null;



function runAIOptimize() {

    const btn = document.getElementById('ai-opt-btn');

    const goal = document.getElementById('ai-opt-goal').value;

    const scope = document.getElementById('bt-scope').value;

    

    btn.disabled = true;

    btn.innerHTML = '<div class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px"></div> Optimizing... (may take 2-5 min)';

    

    document.getElementById('ai-results').style.display = 'none';

    document.getElementById('bt-results').style.display = 'none';

    

    fetch('/?action=ai_optimize&scope=' + scope + '&goal=' + goal, {

        method: 'POST'

    })

    .then(r => r.json())

    .then(data => {

        btn.disabled = false;

        btn.innerHTML = '<span>🤖 AI OPTIMIZE</span>';

        

        if (data.error) {

            alert('Error: ' + data.error);

            return;

        }

        

        displayAIResults(data);

    })

    .catch(err => {

        btn.disabled = false;

        btn.innerHTML = '<span>🤖 AI OPTIMIZE</span>';

        alert('Error: ' + err);

    });

}



function runPortfolioAdvisor() {
    window.location.href = '/advisor';
}


function displayAIResults(data) {

    document.getElementById('ai-results').style.display = 'block';

    

    // Confidence badge

    const confidence = data.confidence || 'medium';

    const confEl = document.getElementById('ai-confidence');

    confEl.className = 'bb-ai-confidence ' + confidence;

    confEl.textContent = confidence.toUpperCase() + ' CONFIDENCE';

    

    // Optimal parameters

    const params = data.best_params || {};

    aiOptimalParams = params;

    

    document.getElementById('ai-optimal-params').innerHTML = `

        <div class="bb-ai-param">

            <span class="bb-ai-param-label">MAX P/E</span>

            <span class="bb-ai-param-value">${params.pe_max || '?'}</span>

        </div>

        <div class="bb-ai-param">

            <span class="bb-ai-param-label">MIN ROE %</span>

            <span class="bb-ai-param-value">${params.roe_min || '?'}</span>

        </div>

        <div class="bb-ai-param">

            <span class="bb-ai-param-label">SELL PE ></span>

            <span class="bb-ai-param-value">${params.pe_sell || '?'}</span>

        </div>

        <div class="bb-ai-param">

            <span class="bb-ai-param-label">MAX DEBT %</span>

            <span class="bb-ai-param-value">${params.debt_equity_max || '?'}</span>

        </div>

        <div class="bb-ai-param">

            <span class="bb-ai-param-label">POSITIONS</span>

            <span class="bb-ai-param-value">${params.max_positions || '?'}</span>

        </div>

    `;

    

    // Expected metrics

    const expected = data.expected_metrics || {};

    document.getElementById('ai-expected-metrics').innerHTML = `

        <div class="bb-ai-expected-item">Expected CAGR: <span>${expected.cagr_estimate || '?'}</span></div>

        <div class="bb-ai-expected-item">Expected Sharpe: <span>${expected.sharpe_estimate || '?'}</span></div>

        <div class="bb-ai-expected-item">Expected MaxDD: <span>${expected.max_drawdown_estimate || '?'}</span></div>

    `;

    

    // Actual best metrics if available

    if (data.best_metrics) {

        const m = data.best_metrics;

        document.getElementById('ai-expected-metrics').innerHTML += `

            <div style="width:100%;margin-top:12px;padding-top:12px;border-top:1px solid #333">

                <span style="color:#00ff00;font-weight:600">ACTUAL RESULTS:</span>

                Return: <span style="color:#00ff00">${(m.total_return||0).toFixed(1)}%</span> |

                CAGR: <span style="color:#00ff00">${(m.cagr||0).toFixed(2)}%</span> |

                Sharpe: <span style="color:#00bfff">${(m.sharpe||0).toFixed(2)}</span> |

                MaxDD: <span style="color:#ff3b30">-${(m.max_drawdown||0).toFixed(1)}%</span>

            </div>

        `;

    }

    

    // Analysis text

    document.getElementById('ai-analysis-text').textContent = data.ai_analysis || 'No analysis available';

    

    // Explanation

    document.getElementById('ai-explanation-text').textContent = data.explanation || 'No explanation available';

    

    // Warnings

    const warnings = data.warnings || [];

    if (warnings.length > 0) {

        document.getElementById('ai-warnings-section').style.display = 'block';

        document.getElementById('ai-warnings-list').innerHTML = warnings.map(w => `<li>${ w }</li>`).join('');

    } else {

        document.getElementById('ai-warnings-section').style.display = 'none';

    }

    

    // Grid results table

    const iterations = data.iterations || [];

    let gridHtml = '';

    iterations.sort((a,b) => (b.metrics?.cagr||0) - (a.metrics?.cagr||0));

    iterations.forEach(it => {

        const p = it.params;

        const m = it.metrics;

        const isOptimal = p.pe_max === params.pe_max && p.roe_min === params.roe_min;

        gridHtml += `<tr style="${isOptimal ? 'background:#1a0033' : ''}">

            <td>${p.pe_max}</td>

            <td>${p.roe_min}%</td>

            <td>${p.debt_equity_max}%</td>

            <td>${p.max_positions}</td>

            <td class="${(m.total_return||0) >= 0 ? 'pos' : 'neg'}">${(m.total_return||0).toFixed(1)}%</td>

            <td>${(m.cagr||0).toFixed(2)}%</td>

            <td>${(m.sharpe||0).toFixed(2)}</td>

            <td style="color:#ff3b30">-${(m.max_drawdown||0).toFixed(1)}%</td>

        </tr>`;

    });

    document.getElementById('ai-grid-body').innerHTML = gridHtml || '<tr><td colspan="8">No data</td></tr>';

    

    // Scroll to results

    document.getElementById('ai-results').scrollIntoView({behavior: 'smooth'});

}



function applyOptimalParams() {

    if (!aiOptimalParams) {

        alert('No optimal parameters available');

        return;

    }

    

    // Apply parameters to form

    document.getElementById('bt-pe-max').value = aiOptimalParams.pe_max || 12;

    document.getElementById('bt-roe-min').value = aiOptimalParams.roe_min || 10;

    document.getElementById('bt-pe-sell').value = aiOptimalParams.pe_sell || 17;

    document.getElementById('bt-debt-max').value = aiOptimalParams.debt_equity_max || 100;

    document.getElementById('bt-max-pos').value = aiOptimalParams.max_positions || 20;

    

    // Run backtest with these params

    runBacktest();

}



// ============= BACKTEST HISTORY =============

let backtestHistoryData = [];

let selectedBacktests = new Set();



function loadBacktestHistory() {

    fetch('/?action=get_backtest_history')

        .then(r => r.json())

        .then(history => {

            backtestHistoryData = history;

            renderBacktestHistory(history);

        })

        .catch(err => {

            document.getElementById('bt-history-body').innerHTML = 

                '<tr><td colspan="9" style="text-align:center;color:#ff3b30">Error loading history</td></tr>';

        });

}



function renderBacktestHistory(history) {

    const tbody = document.getElementById('bt-history-body');

    

    if (!history || history.length === 0) {

        tbody.innerHTML = '<tr><td colspan="14" style="text-align:center;color:#666;padding:20px">No saved backtests yet. Run a backtest and it will be saved automatically.</td></tr>';

        return;

    }

    

    let html = '';

    history.forEach(bt => {

        const m = bt.metrics || {};

        const p = bt.params || {};

        const retClass = (m.total_return || 0) >= 0 ? 'pos' : 'neg';

        const cagrClass = (m.cagr || 0) >= 0 ? 'pos' : 'neg';

        const checked = selectedBacktests.has(bt.id) ? 'checked' : '';

        

        // Format scope

        const scope = (p.universe_scope || 'custom').toUpperCase().substring(0, 3);

        const scopeColor = scope === 'FRA' ? '#00bfff' : scope === 'EUR' ? '#ff9500' : '#888';

        

        // Format rebalancing

        const rebalMap = {'monthly': 'M', 'quarterly': 'Q', 'semi-annual': 'S', 'yearly': 'Y'};

        const rebal = rebalMap[p.rebalance_freq] || p.rebalance_freq || '?';

        

        // Format period (shorter)

        const startY = (p.start_date || '').substring(0, 4);

        const endY = (p.end_date || '').substring(0, 4);

        

        html += `<tr>

            <td><input type="checkbox" class="bt-select" data-id="${bt.id}" ${ checked } onchange="toggleBacktestSelect('${bt.id}')"></td>

            <td class="bb-history-name" onclick="showBacktestDetails('${bt.id}')" title="${bt.name}">${bt.name.length > 20 ? bt.name.substring(0,20)+'...' : bt.name}</td>

            <td style="color:${ scopeColor };font-weight:600">${ scope }</td>

            <td style="color:#888;font-size:10px">${ startY }-${ endY }</td>

            <td style="color:#888">${ rebal }</td>

            <td style="color:#888">${p.pe_max || '?'}/${p.pe_sell || '?'}</td>

            <td style="color:#888">${p.roe_min || '?'}/${p.roe_min_hold || '?'}</td>

            <td style="color:#888">${p.max_positions || '?'}</td>

            <td class="bb-history-metric ${ retClass }">${(m.total_return || 0) >= 0 ? '+' : ''}${(m.total_return || 0).toFixed(1)}%</td>

            <td class="bb-history-metric ${ cagrClass }">${(m.cagr || 0).toFixed(2)}%</td>

            <td>${(m.sharpe || 0).toFixed(2)}</td>

            <td style="color:#ff3b30">-${(m.max_drawdown || 0).toFixed(1)}%</td>

            <td>${(m.win_rate || 0).toFixed(0)}%</td>

            <td class="bb-history-actions">

                <button onclick="renameBacktest('${bt.id}')" title="Rename">âœï¸</button>

                <button onclick="deleteBacktest('${bt.id}')" title="Delete"></button>

            </td>

        </tr>`;

    });

    

    tbody.innerHTML = html;

}



function toggleBacktestSelect(id) {

    if (selectedBacktests.has(id)) {

        selectedBacktests.delete(id);

    } else {

        selectedBacktests.add(id);

    }

    document.getElementById('compare-btn').disabled = selectedBacktests.size < 2;

}



function toggleSelectAll() {

    const checked = document.getElementById('select-all-bt').checked;

    document.querySelectorAll('.bt-select').forEach(cb => {

        cb.checked = checked;

        const id = cb.dataset.id;

        if (checked) selectedBacktests.add(id);

        else selectedBacktests.delete(id);

    });

    document.getElementById('compare-btn').disabled = selectedBacktests.size < 2;

}



function showBacktestDetails(id) {

    const bt = backtestHistoryData.find(b => b.id === id);

    if (!bt) return;

    

    const m = bt.metrics || {};

    const p = bt.params || {};

    

    // Format rebalancing

    const rebalMap = {'monthly': 'Monthly', 'quarterly': 'Quarterly', 'semi-annual': 'Semi-Annual', 'yearly': 'Yearly'};

    const rebal = rebalMap[p.rebalance_freq] || p.rebalance_freq || '?';

    

    alert(`📊 ${bt.name}\n` +

        `â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\n` +

        `🔍… PERIOD\n` +

        `   ${p.start_date} â†’ ${p.end_date}\n` +

        `   Rebalancing: ${ rebal }\n\n` +

        `🌍 SCOPE\n` +

        `   Universe: ${(p.universe_scope || 'custom').toUpperCase()}\n` +

        `   Max Positions: ${p.max_positions || '?'}\n\n` +

        `📈 BUY CRITERIA\n` +

        `   PE <= ${p.pe_max || '?'}\n` +

        `   ROE >= ${p.roe_min || '?'}%\n` +

        `   Debt/Equity <= ${p.debt_equity_max || '?'}%\n\n` +

        `🔍‰ SELL CRITERIA\n` +

        `   PE > ${p.pe_sell || '?'}\n` +

        `   ROE < ${p.roe_min_hold || '?'}%\n\n` +

        `â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n` +

        `💰 RESULTS\n\n` +

        `   Total Return: ${(m.total_return || 0) >= 0 ? '+' : ''}${(m.total_return || 0).toFixed(1)}%\n` +

        `   CAGR: ${(m.cagr || 0).toFixed(2)}%\n` +

        `   Max Drawdown: -${(m.max_drawdown || 0).toFixed(1)}%\n` +

        `   Volatility: ${(m.volatility || 0).toFixed(1)}%\n` +

        `   Sharpe Ratio: ${(m.sharpe || 0).toFixed(2)}\n\n` +

        `   Win Rate: ${(m.win_rate || 0).toFixed(0)}%\n` +

        `   Total Trades: ${m.total_trades || 0}\n` +

        `   Avg Win: +${(m.avg_win || 0).toFixed(1)}%\n` +

        `   Avg Loss: ${(m.avg_loss || 0).toFixed(1)}%\n\n` +

        `   Alpha vs Benchmark: ${(m.alpha || 0) >= 0 ? '+' : ''}${(m.alpha || 0).toFixed(1)}%\n` +

        `   Benchmark Return: ${(m.benchmark_return || 0).toFixed(1)}%`);

}



function renameBacktest(id) {

    const bt = backtestHistoryData.find(b => b.id === id);

    if (!bt) return;

    

    const newName = prompt('Enter new name for this backtest:', bt.name);

    if (newName && newName.trim()) {

        fetch('/?action=rename_backtest&id=' + id + '&name=' + encodeURIComponent(newName.trim()), {method: 'POST'})

            .then(() => loadBacktestHistory())

            .catch(err => alert('Error: ' + err));

    }

}



function deleteBacktest(id) {

    if (!confirm('Delete this backtest?')) return;

    

    fetch('/?action=delete_backtest&id=' + id, {method: 'POST'})

        .then(() => {

            selectedBacktests.delete(id);

            loadBacktestHistory();

        })

        .catch(err => alert('Error: ' + err));

}



function compareSelected() {

    if (selectedBacktests.size < 2) {

        alert('Select at least 2 backtests to compare');

        return;

    }

    

    const selected = backtestHistoryData.filter(bt => selectedBacktests.has(bt.id));

    drawComparisonChart(selected);

}



function drawComparisonChart(backtests) {

    const container = document.getElementById('compare-chart');

    container.style.display = 'block';

    

    const canvas = document.getElementById('compareChart');

    const ctx = canvas.getContext('2d');

    const rect = canvas.parentElement.getBoundingClientRect();

    canvas.width = rect.width - 32;

    canvas.height = 200;

    

    // Clear

    ctx.fillStyle = '#050505';

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    

    // Draw comparison bars

    const metrics = ['total_return', 'cagr', 'sharpe', 'max_drawdown'];

    const metricLabels = ['Total Return %', 'CAGR %', 'Sharpe', 'Max DD %'];

    const colors = ['#00ff00', '#00bfff', '#ff9500', '#9933ff', '#ff3b30', '#ffff00'];

    

    const barWidth = (canvas.width - 100) / metrics.length;

    const groupWidth = barWidth / (backtests.length + 1);

    

    // Find max values for scaling

    let maxVal = 0;

    metrics.forEach(m => {

        backtests.forEach(bt => {

            const val = Math.abs(bt.metrics?.[m] || 0);

            if (val > maxVal) maxVal = val;

        });

    });

    maxVal = maxVal * 1.2 || 100;

    

    const chartHeight = canvas.height - 60;

    const baseY = canvas.height - 40;

    

    // Draw bars

    metrics.forEach((metric, mi) => {

        const x = 60 + mi * barWidth;

        

        backtests.forEach((bt, bi) => {

            let val = bt.metrics?.[metric] || 0;

            if (metric === 'max_drawdown') val = -val;  // Make positive for display

            

            const barH = (Math.abs(val) / maxVal) * (chartHeight / 2);

            const barX = x + bi * groupWidth + 5;

            const barY = val >= 0 ? baseY - barH : baseY;

            

            ctx.fillStyle = colors[bi % colors.length];

            ctx.fillRect(barX, val >= 0 ? barY : baseY, groupWidth - 2, barH);

        });

        

        // Label

        ctx.fillStyle = '#888';

        ctx.font = '9px JetBrains Mono';

        ctx.textAlign = 'center';

        ctx.fillText(metricLabels[mi], x + barWidth / 2, canvas.height - 5);

    });

    

    // Zero line

    ctx.strokeStyle = '#333';

    ctx.beginPath();

    ctx.moveTo(50, baseY);

    ctx.lineTo(canvas.width - 10, baseY);

    ctx.stroke();

    

    // Legend

    ctx.textAlign = 'left';

    backtests.forEach((bt, i) => {

        ctx.fillStyle = colors[i % colors.length];

        ctx.fillRect(10, 10 + i * 15, 10, 10);

        ctx.fillStyle = '#888';

        ctx.font = '9px JetBrains Mono';

        ctx.fillText(bt.name.substring(0, 25), 25, 18 + i * 15);

    });

}



// Load history on page load

setTimeout(loadBacktestHistory, 600);



setInterval(()=>{var now=new Date();document.querySelector('.bb-time').innerHTML=('0'+now.getHours()).slice(-2)+':'+('0'+now.getMinutes()).slice(-2)+':'+('0'+now.getSeconds()).slice(-2)+' CET <span class="blink">●</span>'},1000);


// Portfolio management functions
let editMode = false;
let editTicker = '';

function openAddModal() {
    editMode = false;
    editTicker = '';
    document.getElementById('modal-title').textContent = 'Add Position';
    document.getElementById('pf-ticker').value = '';
    document.getElementById('pf-ticker').disabled = false;
    document.getElementById('pf-name').value = '';
    document.getElementById('pf-qty').value = '';
    document.getElementById('pf-cost').value = '';
    document.getElementById('pf-modal').style.display = 'flex';
}

function editPosition(ticker, name, qty, cost) {
    editMode = true;
    editTicker = ticker;
    document.getElementById('modal-title').textContent = 'Edit Position';
    document.getElementById('pf-ticker').value = ticker;
    document.getElementById('pf-ticker').disabled = true;
    document.getElementById('pf-name').value = name;
    document.getElementById('pf-name').disabled = true;
    document.getElementById('pf-qty').value = qty;
    document.getElementById('pf-cost').value = cost;
    document.getElementById('pf-modal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('pf-modal').style.display = 'none';
    document.getElementById('pf-name').disabled = false;
}

function savePosition() {
    const ticker = document.getElementById('pf-ticker').value.trim().toUpperCase();
    const name = document.getElementById('pf-name').value.trim();
    const qty = parseFloat(document.getElementById('pf-qty').value) || 0;
    const cost = parseFloat(document.getElementById('pf-cost').value) || 0;

    if (!ticker) { alert('Ticker is required'); return; }
    if (qty <= 0) { alert('Quantity must be > 0'); return; }
    if (cost <= 0) { alert('Average cost must be > 0'); return; }

    const action = editMode ? 'editportfolio' : 'addportfolio';
    const url = `/?action=${ action }&ticker=${ ticker }&name=${encodeURIComponent(name)}&qty=${ qty }&avg_cost=${ cost }`;

    fetch(url)
        .then(r => {
            if (r.ok) {
                closeModal();
                location.reload();
            } else {
                return r.text().then(t => { throw new Error(t); });
            }
        })
        .catch(err => alert('Error: ' + err.message));
}

function deletePosition(ticker) {
    if (!confirm('Remove ' + ticker + ' from portfolio?')) return;

    fetch('/?action=rmportfolio&ticker=' + ticker)
        .then(r => {
            if (r.ok) {
                location.reload();
            } else {
                return r.text().then(t => { throw new Error(t); });
            }
        })
        .catch(err => alert('Error: ' + err.message));
}