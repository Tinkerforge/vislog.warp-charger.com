// ---------------------------------------------------------------------------
// Theme toggle (shared across all pages)
// ---------------------------------------------------------------------------
function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-bs-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-bs-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
    // Hook for pages that need extra work (e.g. chart colours)
    if (typeof onThemeChanged === 'function') {
        onThemeChanged(newTheme);
    }
}

function updateThemeIcon(theme) {
    const lightIcon = document.getElementById('theme-icon-light');
    const darkIcon = document.getElementById('theme-icon-dark');
    if (!lightIcon || !darkIcon) return;
    if (theme === 'dark') {
        lightIcon.classList.add('d-none');
        darkIcon.classList.remove('d-none');
    } else {
        lightIcon.classList.remove('d-none');
        darkIcon.classList.add('d-none');
    }
}

// Apply saved theme immediately (before DOMContentLoaded)
(function() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-bs-theme', savedTheme);
    // Icon update deferred until DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            updateThemeIcon(savedTheme);
        });
    } else {
        updateThemeIcon(savedTheme);
    }
})();

// ---------------------------------------------------------------------------
// Signal pickers: focus search on opening and close when keyboard focus leaves.
// ---------------------------------------------------------------------------
document.addEventListener('shown.bs.dropdown', function(e) {
    e.target.closest('.chart-toolbar')?.querySelector('.chart-signal-search')?.focus();
});

document.addEventListener('focusout', function(e) {
    const dropdown = e.target.closest('.chart-toolbar .dropdown');
    if (dropdown && e.relatedTarget && !dropdown.contains(e.relatedTarget)) {
        bootstrap.Dropdown.getInstance(dropdown.querySelector('[data-bs-toggle="dropdown"]'))?.hide();
    }
});

// ---------------------------------------------------------------------------
// Shared URL hash helpers – read/modify/write individual params without
// clobbering unrelated ones (e.g. tab, cols, cm, log all coexist).
// ---------------------------------------------------------------------------
function _hashParams() {
    return new URLSearchParams(location.hash.slice(1));
}

function _hashSet(key, value) {
    const params = _hashParams();
    if (value === null || value === undefined || value === '') {
        params.delete(key);
    } else {
        params.set(key, value);
    }
    history.replaceState(null, '', '#' + params.toString());
    _updateTabLinks();
}

function _updateTabLinks() {
    document.querySelectorAll('.nav-tabs-vislog .nav-link[data-bs-target]').forEach(link => {
        const params = _hashParams();
        params.set('tab', link.id);
        link.href = location.pathname + location.search + '#' + params.toString();
    });
}

function _parseChartHash(colsKey, logKey) {
    const params = _hashParams();
    const colParam = params.get(colsKey);
    const columns = colParam !== null ? colParam.split(',').filter(Boolean) : null;
    const log = params.get(logKey) === '1';
    return { columns, log };
}

function _updateChartHash(checkboxSelector, logCheckboxId, colsKey, logKey) {
    const selected = [];
    document.querySelectorAll(checkboxSelector + ':checked').forEach(cb => {
        selected.push(cb.dataset.column);
    });
    const logCb = document.getElementById(logCheckboxId);
    const useLog = logCb && logCb.checked;

    const params = _hashParams();
    // An explicit empty selection must survive reloads and shared links.
    params.set(colsKey, selected.join(','));
    if (useLog) {
        params.set(logKey, '1');
    } else {
        params.delete(logKey);
    }
    history.replaceState(null, '', '#' + params.toString());
    _updateTabLinks();
}

// ---------------------------------------------------------------------------
// Zoom URL hash helpers, persist / restore chart zoom level in the URL so
// that a shared link reproduces the same view.
// ---------------------------------------------------------------------------
function _saveZoomToHash(chart, xKey, yKey) {
    if (!chart) return;
    const xScale = chart.scales.x;
    const yScale = chart.scales.y;
    if (xScale && xScale.min != null && xScale.max != null) {
        _hashSet(xKey, xScale.min + ',' + xScale.max);
    }
    if (yScale && yScale.min != null && yScale.max != null) {
        _hashSet(yKey, yScale.min + ',' + yScale.max);
    }
}

function _applyZoomFromHash(chart, xKey, yKey) {
    if (!chart) return;
    const params = _hashParams();
    const xZoom = params.get(xKey);
    const yZoom = params.get(yKey);
    if (xZoom) {
        const parts = xZoom.split(',').map(Number);
        if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
            chart.zoomScale('x', {min: parts[0], max: parts[1]}, 'none');
        }
    }
    if (yZoom) {
        const parts = yZoom.split(',').map(Number);
        if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
            chart.zoomScale('y', {min: parts[0], max: parts[1]}, 'none');
        }
    }
}

function _clearZoomHash(xKey, yKey) {
    _hashSet(xKey, null);
    _hashSet(yKey, null);
}

// ---------------------------------------------------------------------------
// Tab persistence – save active tab in URL hash, restore on page load.
// Works on both protocol and report pages.
// ---------------------------------------------------------------------------
document.addEventListener('shown.bs.tab', function(e) {
    const tabId = e.target.id;  // e.g. "chart-tab", "config-tab"
    if (tabId) _hashSet('tab', tabId);
});

document.addEventListener('DOMContentLoaded', function() {
    // Migrate links to the former top-level configuration and event-log tabs.
    const oldTab = _hashParams().get('tab') || '';
    const oldSnapshotTab = /^(before|after)-(json|log)-tab$/.exec(oldTab);
    if (oldSnapshotTab && oldSnapshotTab[2] === 'log' && document.getElementById('protocol-event-log')) {
        _hashSet('tab', 'log-tab');
    } else if (document.getElementById('protocol-json')) {
        if (oldSnapshotTab && oldSnapshotTab[2] === 'json') {
            _hashSet('tab', 'config-tab');
        } else if (oldTab === 'config-diff-tab') {
            _hashSet('tab', 'config-tab');
            _hashSet('config', 'diff');
        }
    }
    _updateTabLinks();

    document.querySelectorAll('.nav-tabs-vislog .nav-link[data-bs-target]').forEach(function(link) {
        link.addEventListener('click', function(e) {
            e.stopPropagation();
            if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
            e.preventDefault();
            bootstrap.Tab.getOrCreateInstance(link).show();
        });
    });

    const params = _hashParams();
    const tabId = params.get('tab');
    if (tabId) {
        const tabEl = document.getElementById(tabId);
        if (tabEl) {
            const tab = new bootstrap.Tab(tabEl);
            tab.show();
        }
    }

    // Preserve query string + hash when switching language
    document.querySelectorAll('.btn-lang').forEach(function(link) {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = link.getAttribute('href') + location.search + location.hash;
        });
    });
});


// ---------------------------------------------------------------------------
// Shared chart infrastructure – colors, factory, helpers
// ---------------------------------------------------------------------------
const CHART_COLORS = [
    '#2563eb', '#c65d12', '#0d8875', '#cf375b', '#8250cf',
    '#087f9c', '#9b7500', '#b044aa', '#4e7d20', '#64748b',
    '#4263c7', '#ae4c27', '#19734b', '#b52c40', '#664ac4',
    '#16798a', '#a06415', '#a93d79', '#567222', '#526780',
    '#3277ba', '#bc6829', '#27826c', '#c04f70', '#9451b7',
    '#278099', '#8d7618', '#ae498f', '#6c7b25', '#68718e',
];
const CHART_COLORS_DARK = [
    '#60a5fa', '#fb923c', '#34d3b0', '#fb7185', '#b197fc',
    '#38c8e8', '#e5bf52', '#e78bd6', '#a3c969', '#a0aec0',
    '#8ba4fa', '#e8a07c', '#68c895', '#ed8f9c', '#a99aee',
    '#6cc9d4', '#e2b16f', '#d48ab4', '#b4c585', '#91aacb',
    '#77b8ec', '#dba16e', '#83c9b7', '#dc9ab0', '#c49bdd',
    '#81c8dc', '#cabe78', '#d29bc0', '#c2ca8c', '#a9b1ce',
];

function chartSignalColor(index) {
    const colors = document.documentElement.getAttribute('data-bs-theme') === 'dark'
        ? CHART_COLORS_DARK : CHART_COLORS;
    return colors[index % colors.length];
}

// The crosshair follows the inspected sample; the HTML inspector keeps labels
// and values readable without changing the chart's data or layout.
const chartPresentationPlugin = {
    id: 'chartPresentation',
    beforeDraw(chart) {
        const {ctx, chartArea: area} = chart;
        if (!area) return;
        const dark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
        ctx.save();
        ctx.fillStyle = dark ? '#ffffff03' : '#f5f8fc';
        ctx.fillRect(area.left, area.top, area.width, area.height);
        ctx.strokeStyle = dark ? '#94a3b81c' : '#64748b20';
        ctx.lineWidth = 1;
        ctx.strokeRect(area.left, area.top, area.width, area.height);
        ctx.restore();
    },
    afterDatasetsDraw(chart) {
        const active = chart.tooltip?.getActiveElements() || [];
        if (!active.length || !chart.tooltip.opacity) return;
        const {ctx, chartArea: area} = chart;
        const x = active[0].element.x;
        if (x < area.left || x > area.right) return;
        const dark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
        ctx.save();
        ctx.beginPath();
        ctx.rect(area.left, area.top, area.width, area.height);
        ctx.clip();
        ctx.strokeStyle = dark ? '#cbd5e180' : '#47556980';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 4]);
        ctx.beginPath();
        ctx.moveTo(x, area.top);
        ctx.lineTo(x, area.bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        active.forEach(({element, datasetIndex}) => {
            if (element.skip) return;
            ctx.beginPath();
            ctx.arc(element.x, element.y, 3.5, 0, Math.PI * 2);
            ctx.fillStyle = chart.data.datasets[datasetIndex].borderColor;
            ctx.fill();
            ctx.strokeStyle = dark ? '#18212f' : '#ffffff';
            ctx.lineWidth = 1.5;
            ctx.stroke();
        });
        ctx.restore();
    },
    afterDestroy(chart) {
        chart.$inspector?.remove();
    },
};

const chartLegendPlugin = {
    id: 'htmlSignalLegend',
    afterUpdate(chart, args, options) {
        if (!chart.$legend) {
            const legend = document.createElement('div');
            legend.className = 'chart-signal-legend';
            legend.setAttribute('role', 'group');
            legend.setAttribute('aria-label', T.select_columns_heading);
            chart.canvas.parentElement.after(legend);
            chart.$legend = legend;
        }
        const legend = chart.$legend;
        chart.data.datasets.forEach((dataset, index) => {
            let button = legend.children[index];
            if (!button) {
                button = document.createElement('button');
                button.type = 'button';
                button.className = 'chart-legend-signal';
                const swatch = document.createElement('span');
                swatch.className = 'chart-legend-swatch';
                swatch.setAttribute('aria-hidden', 'true');
                const label = document.createElement('span');
                label.className = 'chart-legend-label';
                button.append(swatch, label);
                const highlight = () => {
                    chart.$highlightedSignal = chart.isDatasetVisible(index) ? index : null;
                    chart.draw();
                };
                const clear = () => { chart.$highlightedSignal = null; chart.draw(); };
                button.addEventListener('mouseenter', highlight);
                button.addEventListener('mouseleave', clear);
                button.addEventListener('focus', highlight);
                button.addEventListener('blur', clear);
                button.addEventListener('click', () => {
                    const visible = !chart.isDatasetVisible(index);
                    chart.setDatasetVisibility(index, visible);
                    chart.$highlightedSignal = null;
                    chart.setActiveElements([]);
                    chart.tooltip.setActiveElements([], {x: 0, y: 0});
                    if (chart.$inspector) chart.$inspector.hidden = true;
                    if (options.pickerPrefix) {
                        const picker = document.getElementById(options.pickerPrefix + '-signal-picker');
                        const checkbox = Array.from(picker.querySelectorAll('input[data-column]'))
                            .find(cb => cb.dataset.column === chart.data.datasets[index].signalKey);
                        if (checkbox) checkbox.checked = visible;
                        updateChartPicker(options.pickerPrefix);
                        if (options.pickerPrefix === 'proto') _protoUpdateHash();
                        else _cmUpdateHash();
                    }
                    chart.update('none');
                });
                legend.appendChild(button);
            }
            button.firstChild.style.backgroundColor = dataset.borderColor;
            button.lastChild.textContent = dataset.label;
            button.title = dataset.label;
            button.setAttribute('aria-pressed', String(chart.isDatasetVisible(index)));
        });
        while (legend.children.length > chart.data.datasets.length) legend.lastChild.remove();
        legend.hidden = !chart.data.datasets.length;
    },
    beforeDatasetDraw(chart, {index}) {
        chart.ctx.save();
        // Preview removal: dim the hovered/focused signal, keeping others clear.
        if (chart.$highlightedSignal === index) chart.ctx.globalAlpha = 0.2;
    },
    afterDatasetDraw(chart) {
        chart.ctx.restore();
    },
    afterDestroy(chart) {
        chart.$legend?.remove();
    },
};

function chartInspectorLabel(dataset) {
    const label = dataset.label || '';
    // Only move explicit, recognized unit suffixes; descriptive parentheses and
    // raw signal names are not reliable sources of units.
    const match = /\s*(?:\((mA|A|mV|V|kW|W|kWh|Wh|Ohm|Ω|%|% Duty Cycle|ms|s|Hz|°C)\)|\[(mA|A|mV|V|kW|W|kWh|Wh|Ohm|Ω|%|ms|s|Hz|°C)\])$/.exec(label);
    const unit = match ? match[1] || match[2] : dataset.inspectorUnit || '';
    return {
        label: match ? label.slice(0, match.index) : label,
        unit: unit === 'Ohm' ? 'Ω' : unit === '% Duty Cycle' ? '%' : unit,
    };
}

function chartHoverInspector({chart, tooltip}) {
    if (!tooltip.opacity) {
        if (chart.$inspector) chart.$inspector.hidden = true;
        return;
    }
    if (!chart.$inspector) {
        chart.$inspector = document.createElement('div');
        chart.$inspector.className = 'chart-hover-inspector';
        chart.$inspector.setAttribute('role', 'tooltip');
        chart.canvas.parentElement.appendChild(chart.$inspector);
    }
    const inspector = chart.$inspector;
    inspector.hidden = false;
    inspector.replaceChildren();
    const title = document.createElement('div');
    title.className = 'chart-hover-time';
    title.textContent = (tooltip.title || []).join(' · ');
    inspector.appendChild(title);
    const number = new Intl.NumberFormat(document.documentElement.lang || 'en', {maximumSignificantDigits: 8});
    const rowLimit = Math.max(1, Math.min(12, Math.floor((Math.min(chart.height, window.innerHeight * 0.6) - 80) / 26)));
    const items = tooltip.dataPoints || [];
    items.slice(0, rowLimit).forEach(item => {
        const row = document.createElement('div');
        row.className = 'chart-hover-row';
        const dot = document.createElement('span');
        dot.className = 'chart-signal-color';
        dot.style.backgroundColor = item.dataset.borderColor;
        const label = document.createElement('span');
        label.className = 'chart-hover-label';
        const description = chartInspectorLabel(item.dataset);
        label.textContent = description.label;
        const value = document.createElement('span');
        value.className = 'chart-hover-value';
        // Logarithmic plots substitute 0.01 for zero; show the recorded value.
        const y = item.dataset.inspectorValues?.[item.dataIndex] ?? item.parsed.y;
        value.textContent = Number.isFinite(y) ? number.format(y) : '—';
        const unit = document.createElement('span');
        unit.className = 'chart-hover-unit';
        unit.textContent = description.unit;
        row.append(dot, label, value, unit);
        inspector.appendChild(row);
    });
    if (items.length > rowLimit) {
        const more = document.createElement('div');
        more.className = 'chart-hover-more';
        more.textContent = T.chart_more_signals.replace('${count}', items.length - rowLimit);
        inspector.appendChild(more);
    }
    const canvas = chart.canvas.getBoundingClientRect();
    const parent = chart.canvas.parentElement.getBoundingClientRect();
    const x = canvas.left - parent.left + tooltip.caretX;
    const y = canvas.top - parent.top + tooltip.caretY;
    const width = inspector.offsetWidth;
    const left = x + 16 + width <= parent.width - 8 ? x + 16 : x - width - 16;
    inspector.style.left = Math.max(8, Math.min(left, parent.width - width - 8)) + 'px';
    inspector.style.top = Math.max(8, Math.min(y - 20, parent.height - inspector.offsetHeight - 8)) + 'px';
}

/**
 * Create (or recreate) a time-series Chart.js line chart.
 *
 * @param {Object} cfg
 * @param {string}        cfg.canvasId           - canvas element id
 * @param {Chart|null}    cfg.prevChart          - previous Chart instance to destroy (or null)
 * @param {Array}         cfg.labels             - x-axis labels
 * @param {Array}         cfg.datasets           - Chart.js dataset objects
 * @param {string}        cfg.titleText          - chart title
 * @param {boolean}       cfg.useLog             - use logarithmic y-axis
 * @param {Function}      [cfg.xTickCallback]    - custom x-axis tick callback
 * @param {Function}      [cfg.tooltipTitleCallback] - custom tooltip title callback
 * @param {number}        [cfg.xMaxTicksLimit]   - max x-axis tick count
 * @param {string}        [cfg.xTitle]           - x-axis title text
 * @param {string}        [cfg.yTitle]           - y-axis title text
 * @param {string}        [cfg.zoomXKey]         - URL hash key for x-axis zoom (enables zoom persistence)
 * @param {string}        [cfg.zoomYKey]         - URL hash key for y-axis zoom
 * @param {Object}        [cfg.xScale]           - x-axis overrides (e.g. numeric time bounds)
 * @param {Array}         [cfg.plugins]          - chart-local plugins
 * @param {string}        [cfg.pickerPrefix]     - synchronize legend with signal picker
 * @returns {Chart}       the new Chart instance
 */
function _createTimeSeriesChart(cfg) {
    const canvas = document.getElementById(cfg.canvasId);
    if (!canvas) return null;
    canvas.parentElement.classList.add('chart-surface');

    if (cfg.prevChart) {
        cfg.prevChart.destroy();
    }

    const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    const textColor = isDark ? '#f0f0f0' : '#212529';
    const gridColor = isDark ? '#94a3b814' : '#64748b14';
    const tickFont = {size: 12, family: 'system-ui, sans-serif'};

    const yScale = {
        display: true,
        ticks: { color: textColor, font: tickFont, padding: 8, maxTicksLimit: 7 },
        grid: { color: gridColor, drawTicks: false },
        border: {display: false},
    };
    if (cfg.useLog) {
        yScale.type = 'logarithmic';
    }
    if (cfg.yTitle) {
        yScale.title = { display: true, text: cfg.yTitle, color: textColor };
    }

    const xTicks = { color: textColor, font: tickFont, padding: 8, maxRotation: 0, maxTicksLimit: 9 };
    if (cfg.xTickCallback) xTicks.callback = cfg.xTickCallback;
    if (cfg.xMaxTicksLimit) xTicks.maxTicksLimit = cfg.xMaxTicksLimit;

    const xScale = {
        display: true,
        ticks: xTicks,
        grid: { color: gridColor, drawTicks: false },
        border: {display: false},
    };
    if (cfg.xScale) Object.assign(xScale, cfg.xScale);
    if (cfg.xTitle) {
        xScale.title = { display: true, text: cfg.xTitle, color: textColor };
    }

    const tooltipCallbacks = {};
    if (cfg.tooltipTitleCallback) {
        tooltipCallbacks.title = cfg.tooltipTitleCallback;
    }

    const chart = new Chart(canvas, {
        type: 'line',
        plugins: [chartPresentationPlugin, chartLegendPlugin, ...(cfg.plugins || [])],
        data: { labels: cfg.labels, datasets: cfg.datasets },
        options: {
            animation: false,
            locale: document.documentElement.lang || 'en',
            layout: {padding: {top: 12, left: 4, right: 12}},
            onResize(chart, size) {
                chart.options.scales.x.ticks.maxTicksLimit = Math.max(2,
                    Math.min(cfg.xMaxTicksLimit || 9, Math.floor(size.width / 110)));
                if (chart.$inspector) chart.$inspector.hidden = true;
            },
            maintainAspectRatio: false,
            elements: { point: { radius: 0 } },
            interaction: { mode: 'index', axis: 'x', intersect: false },
            plugins: {
                title: {
                    display: !!cfg.titleText,
                    text: cfg.titleText,
                    color: textColor,
                },
                tooltip: {
                    enabled: false,
                    external: chartHoverInspector,
                    mode: 'index',
                    axis: 'x',
                    intersect: false,
                    callbacks: tooltipCallbacks,
                },
                legend: {
                    display: false,
                    labels: { color: textColor, font: tickFont, usePointStyle: true,
                        pointStyle: 'line', boxWidth: 20, padding: 16 },
                    position: 'bottom',
                },
                htmlSignalLegend: {pickerPrefix: cfg.pickerPrefix},
                zoom: {
                    zoom: {
                        drag: {
                            enabled: true,
                            backgroundColor: 'rgba(96, 165, 250, 0.12)',
                            borderColor: 'rgba(96, 165, 250, 0.65)',
                            borderWidth: 1,
                            threshold: 20,
                        },
                        wheel: { enabled: false },
                        mode: 'xy',
                        onZoomComplete: function({chart}) {
                            if (cfg.zoomXKey) _saveZoomToHash(chart, cfg.zoomXKey, cfg.zoomYKey);
                        },
                    },
                    pan: {
                        enabled: true,
                        mode: 'xy',
                        modifierKey: 'ctrl',
                        threshold: 5,
                        onPanComplete: function({chart}) {
                            if (cfg.zoomXKey) _saveZoomToHash(chart, cfg.zoomXKey, cfg.zoomYKey);
                        },
                    }
                }
            },
            scales: {
                x: xScale,
                y: yScale
            }
        }
    });

    // Restore zoom from URL hash if present
    if (cfg.zoomXKey) {
        _applyZoomFromHash(chart, cfg.zoomXKey, cfg.zoomYKey);
    }

    return chart;
}

/**
 * Build a single Chart.js dataset object from raw data.
 */
function _chartDataset(label, data, colorIdx) {
    const color = chartSignalColor(colorIdx);
    return {
        label: label,
        data: data,
        borderColor: color,
        backgroundColor: color + '33',
        borderWidth: 1.8,
        pointHoverRadius: 0,
        pointRadius: 0,
        tension: 0,
        fill: false,
    };
}

/**
 * Select/deselect all checkboxes in a container and re-render the chart.
 */
function chartSelectAll(checkboxSelector, checked, renderFn) {
    document.querySelectorAll(checkboxSelector).forEach(cb => {
        cb.checked = checked;
    });
    renderFn();
}

function initChartPicker(prefix, columns) {
    const picker = document.getElementById(prefix + '-signal-picker');
    if (!picker) return;
    const indices = new Map(columns.map((column, index) => [column, index]));
    picker.querySelectorAll('input[data-column]').forEach(cb => {
        const label = cb.closest('label');
        label.title = cb.dataset.column;
        const dot = document.createElement('span');
        dot.className = 'chart-signal-color';
        dot.setAttribute('aria-hidden', 'true');
        cb.dataset.colorIndex = indices.get(cb.dataset.column);
        dot.style.backgroundColor = chartSignalColor(indices.get(cb.dataset.column));
        cb.after(dot);
        const text = document.createElement('span');
        text.className = 'chart-signal-label';
        while (dot.nextSibling) text.appendChild(dot.nextSibling);
        dot.after(text);
    });
    picker.querySelectorAll('.chart-column-group h6').forEach(heading => {
        const count = document.createElement('span');
        count.className = 'chart-group-count';
        heading.appendChild(count);
    });
    updateChartPicker(prefix);
}

function updateChartPicker(prefix) {
    const picker = document.getElementById(prefix + '-signal-picker');
    if (!picker) return;
    const search = document.getElementById(prefix + '-signal-search');
    const terms = search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const selectedOnly = document.getElementById(prefix + '-selected-only').checked;
    let selected = 0;
    let visible = 0;
    picker.querySelectorAll('.chart-column-group').forEach(group => {
        let groupSelected = 0;
        let groupVisible = 0;
        const inputs = group.querySelectorAll('input[data-column]');
        inputs.forEach(cb => {
            const label = cb.closest('label');
            const dot = label.querySelector('.chart-signal-color');
            if (dot) dot.style.backgroundColor = chartSignalColor(Number(cb.dataset.colorIndex));
            const haystack = (cb.dataset.column + ' ' + label.textContent).toLocaleLowerCase();
            label.hidden = (selectedOnly && !cb.checked) || !terms.every(term => haystack.includes(term));
            if (label.hidden && label.contains(document.activeElement)) search.focus();
            if (!label.hidden) groupVisible++;
            if (cb.checked) groupSelected++;
        });
        group.hidden = groupVisible === 0;
        const count = group.querySelector('.chart-group-count');
        if (count) count.textContent = ` ${groupSelected}/${inputs.length}`;
        selected += groupSelected;
        visible += groupVisible;
    });
    picker.querySelector('[data-signal-count]').textContent = selected;
    picker.querySelector('[data-signal-empty]').hidden = visible !== 0;
}

function chartRestoreDefaults(prefix, renderFn) {
    const picker = document.getElementById(prefix + '-signal-picker');
    picker.querySelectorAll('input[data-column]').forEach(cb => { cb.checked = cb.defaultChecked; });
    document.getElementById(prefix + '-signal-search').value = '';
    document.getElementById(prefix + '-selected-only').checked = false;
    renderFn();
}

/**
 * Reset zoom on a Chart.js instance and clear zoom hash params.
 */
function chartResetZoom(chartRef, xKey, yKey) {
    if (chartRef) chartRef.resetZoom();
    if (xKey) _clearZoomHash(xKey, yKey);
}

function _detectHwVersion(json) {
    // Detect hardware version from report/protocol JSON.
    // Returns the Version IntFlag value matching the api_doc_generator Version enum.
    const VERSION_MAP = {
        'warp':  1,  // WARP1
        'warp2': 2,  // WARP2
        'warp3': 4,  // WARP3
        'warp4': 32, // WARP4
        'wem':   8,  // WEM
        'wem2':  16, // WEM2
    };
    const deviceType = json?.['info/name']?.type;
    if (deviceType && VERSION_MAP[deviceType] !== undefined) {
        return VERSION_MAP[deviceType];
    }
    return -1; // ANY
}

function _resolveFieldEntry(node, apiDocs) {
    // Resolve the API doc entry for a leaf node.
    // Returns {fieldEntry, apiPath} or null if not found.
    const fieldKey = node.key;
    if (fieldKey === undefined || fieldKey === null) return null;

    let apiPath = null;
    let isArrayChild = false;
    let current = node.parent;
    while (current) {
        if (current.key !== undefined && current.key !== null) {
            if (typeof current.key === 'string' && current.key.includes('/')) {
                apiPath = current.key;
                break;
            }
            if (!isNaN(current.key)) {
                isArrayChild = true;
            }
        }
        current = current.parent;
    }

    if (!apiPath) return null;

    const pathDocs = apiDocs[apiPath];
    if (!pathDocs) return null;

    let fieldEntry = pathDocs[fieldKey];
    if (!fieldEntry && isArrayChild && pathDocs._array_members) {
        fieldEntry = pathDocs._array_members[fieldKey];
    }

    if (!fieldEntry || typeof fieldEntry !== 'object' || Array.isArray(fieldEntry)) return null;

    return { fieldEntry, apiPath };
}

function _annotateTree(tree, apiDocs, hwVersion) {
    // Single-pass tree traversal that annotates leaf values with constant
    // descriptions, unit abbreviations, and clickable info buttons.
    jsonview.traverse(tree, function(node) {
        if (!node.el) return;

        // Handle censored null values: show explanatory text instead of "null"
        if (node.value === null || node.value === undefined) {
            const resolved = _resolveFieldEntry(node, apiDocs);
            if (resolved && resolved.fieldEntry && resolved.fieldEntry.censored) {
                const valueEl = node.el.querySelector('.json-value');
                if (valueEl) {
                    valueEl.textContent = `*${T.censored_value || 'censored in debug report'}*`;
                    valueEl.classList.add('json-censored');
                }
            }
            return;
        }
        if (typeof node.value === 'object') return; // skip objects/arrays

        const resolved = _resolveFieldEntry(node, apiDocs);
        if (!resolved) return;

        const { fieldEntry } = resolved;
        const valueEl = node.el.querySelector('.json-value');

        // --- constant & unit annotations on the value element ------------
        if (valueEl) {
            const constants = fieldEntry.constants;
            if (constants && Array.isArray(constants)) {
                const nodeVal = node.value;
                let matchDesc = null;

                for (const c of constants) {
                    if (c.version !== -1 && hwVersion !== -1 && (c.version & hwVersion) === 0) {
                        continue;
                    }
                    if (typeof nodeVal === 'boolean') {
                        if (c.val === String(nodeVal)) { matchDesc = c.desc; break; }
                    } else if (typeof nodeVal === 'number') {
                        if (c.val === nodeVal) { matchDesc = c.desc; break; }
                    } else if (typeof nodeVal === 'string') {
                        if (c.val === nodeVal) { matchDesc = c.desc; break; }
                    }
                }

                if (matchDesc) {
                    const hintEl = document.createElement('span');
                    hintEl.className = 'enum-hint';
                    hintEl.textContent = ` (${matchDesc})`;
                    hintEl.title = matchDesc;
                    valueEl.appendChild(hintEl);
                }
            }

            if (fieldEntry.unit) {
                const unitEl = document.createElement('span');
                unitEl.className = 'unit-hint';
                unitEl.textContent = ` ${fieldEntry.unit.abbr}`;
                unitEl.title = fieldEntry.unit.name;
                valueEl.appendChild(unitEl);
            }
        }

        // --- info button with popover ------------------------------------
        if (!fieldEntry.desc) return;

        let bodyHtml = `<div class="field-info-body">`;
        bodyHtml += `<p class="field-info-desc">${_escapeHtml(fieldEntry.desc)}</p>`;

        if (fieldEntry.unit) {
            bodyHtml += `<p class="field-info-unit">${_escapeHtml(T.popover_unit)}: <strong>${_escapeHtml(fieldEntry.unit.name)}</strong> (${_escapeHtml(fieldEntry.unit.abbr)})</p>`;
        }

        if (fieldEntry.constants && fieldEntry.constants.length > 0) {
            const relevantConsts = fieldEntry.constants.filter(c =>
                c.version === -1 || hwVersion === -1 || (c.version & hwVersion) !== 0
            );
            if (relevantConsts.length > 0) {
                bodyHtml += `<div class="field-info-constants"><strong>${_escapeHtml(T.popover_values)}</strong><table class="field-info-table">`;
                for (const c of relevantConsts) {
                    bodyHtml += `<tr><td class="field-info-val">${_escapeHtml(String(c.val))}</td><td>${_escapeHtml(c.desc)}</td></tr>`;
                }
                bodyHtml += `</table></div>`;
            }
        }

        bodyHtml += `</div>`;

        const btn = document.createElement('i');
        btn.className = 'bi bi-info-circle field-info-btn';
        btn.setAttribute('tabindex', '0');
        btn.setAttribute('role', 'button');

        node.el.insertBefore(btn, node.el.firstChild);

        new bootstrap.Popover(btn, {
            html: true,
            content: bodyHtml,
            placement: 'right',
            trigger: 'focus',
            fallbackPlacements: ['right', 'left', 'top', 'bottom'],
            customClass: 'field-info-popover',
        });
    });
}

function _escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function make_jsonview(json, selector, options = {}) {
    const container = document.querySelector(selector);
    const tree = jsonview.create(json);
    const savedConfigs = new Set(Array.isArray(json.modified) ? json.modified : []);
    const apiConstants = options.apiConstants || null;
    const hwVersion = options.hwVersion || -1;  // -1 = ANY

    // Create enhanced JSON viewer container
    const wrapper = document.createElement('div');
    wrapper.className = 'enhanced-json-viewer';

    // Add search and filter controls
    const controls = document.createElement('div');
    controls.className = 'json-controls';
    controls.innerHTML = `
        <div class="json-search-container">
            <input type="text" class="json-search form-control" placeholder="${T.search_placeholder}" />
            <div class="search-results-count"></div>
        </div>
        <div class="json-filters-actions">
            <div class="json-filters btn-group btn-group-sm">
                <button class="btn btn-outline-secondary active" data-filter="all" title="${T.filter_all_title}">${T.filter_all}</button>
                ${options.comparison ? `<button class="btn btn-outline-secondary" data-filter="differences">${T.config_only_differences}</button>` : ''}
                <button class="btn btn-outline-secondary" data-filter="modified" title="${T.filter_modified_title}">${T.filter_modified}</button>
                <button class="btn btn-outline-secondary" data-filter="numbers" title="${T.filter_numbers_title}">${T.filter_numbers}</button>
                <button class="btn btn-outline-secondary" data-filter="strings" title="${T.filter_strings_title}">${T.filter_strings}</button>
                <button class="btn btn-outline-secondary" data-filter="booleans" title="${T.filter_booleans_title}">${T.filter_booleans}</button>
                <button class="btn btn-outline-secondary" data-filter="objects" title="${T.filter_objects_title}">${T.filter_objects}</button>
            </div>
            <div class="json-actions btn-group btn-group-sm">
                <button class="btn btn-outline-primary" onclick="expandAllJson('${selector}')" title="${T.expand_all_title}">${T.expand_all}</button>
                <button class="btn btn-outline-primary" onclick="collapseAllJson('${selector}')" title="${T.collapse_all_title}">${T.collapse_all}</button>
            </div>
        </div>
    `;

    // Create JSON content container
    const jsonContent = document.createElement('div');
    jsonContent.className = 'json-content';

    // Create legend for colored line highlights
    const legend = document.createElement('div');
    legend.className = 'json-legend';
    legend.innerHTML = `
        <span class="json-legend-item">
            <span class="json-legend-swatch json-legend-modified"></span> ${T.legend_modified}
        </span>
        <span class="json-legend-item">
            <span class="json-legend-swatch json-legend-important"></span> ${T.legend_important}
        </span>
        <span class="json-legend-item">
            <i class="bi bi-info-circle json-legend-info-icon"></i> ${T.legend_info}
        </span>
    `;

    wrapper.appendChild(controls);
    wrapper.appendChild(legend);
    wrapper.appendChild(jsonContent);
    container.innerHTML = '';
    container.appendChild(wrapper);

    // Scalar arrays are leaf values in the configuration table, not one row per index.
    if (options.treeTable) {
        jsonview.traverse(tree, node => {
            if (isInlineConfigArray(node.value)) node.children = [];
        });
    }

    // Render JSON tree
    // The vendor renderer interpolates strings as HTML. Escape only for rendering,
    // then restore the original data for comparison, search and API annotations.
    const originalStrings = [];
    jsonview.traverse(tree, node => {
        for (const property of ['key', 'value']) {
            if (typeof node[property] === 'string') {
                originalStrings.push([node, property, node[property]]);
                node[property] = _escapeHtml(node[property]);
            }
        }
    });
    jsonview.render(tree, jsonContent);
    originalStrings.forEach(([node, property, value]) => { node[property] = value; });
    jsonview.expand(tree);

    // Store tree reference on the container for later use
    container._jsonTree = tree;    // Enhanced highlighting and processing
    jsonview.traverse(tree, function(node) {
        // Add data type classes
        if (node.el && node.value !== null) {
            const valueType = typeof node.value;
            node.el.classList.add(`json-type-${valueType}`);

            // Add timestamp formatting, only for plausible real-world dates
            // (uptimes, boot_ids, bitmasks, etc. also fall into the Unix range
            //  but decode to implausible years like 2057 or 2106)
            if (typeof node.value === 'number' && node.value > 1000000000 && node.value < 9999999999) {
                const date = new Date(node.value * 1000);
                const year = date.getFullYear();
                if (!isNaN(year) && year >= 2020 && year <= new Date().getFullYear() + 2) {
                    const timeEl = document.createElement('span');
                    timeEl.className = 'timestamp-hint';
                    timeEl.textContent = ` (${date.toLocaleString()})`;
                    const valueEl = node.el.querySelector('.json-value');
                    if (valueEl) valueEl.appendChild(timeEl);
                }
            }
        }

        if (node.parent === tree && typeof node.key === 'string' && node.el) {
            // The new list contains filenames: flatten API paths, not underscores
            // in filenames (wifi/sta_config -> wifi_sta_config).
            const saved = savedConfigs.has(node.key.replace(/\//g, '_'));
            const legacy = json[node.key + '_modified']?.modified;
            if (saved || legacy == 1 || legacy == 2 || legacy == 3) {
                node.el.classList.add('modified-config');
            }
            if (legacy == 1 || legacy == 3) {
                node.el.classList.add('important');
            }
        }
    });

    // Annotate leaf values with API doc constant descriptions and units;
    // add info buttons with Bootstrap popovers for field documentation.
    if (apiConstants) {
        _annotateTree(tree, apiConstants, hwVersion);
    }
    if (options.comparison) annotateConfigComparison(tree, options.comparison);
    if (options.treeTable) layoutConfigTree(tree, jsonContent, options);

    // Add search functionality
    const searchInput = wrapper.querySelector('.json-search');
    const resultsCount = wrapper.querySelector('.search-results-count');
    let searchResults = [];
    let currentSearchIndex = -1;

    searchInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase();
        searchResults = [];
        currentSearchIndex = -1;

        // Clear previous highlights
        wrapper.querySelectorAll('.search-highlight').forEach(el => {
            el.classList.remove('search-highlight', 'search-current');
        });

        if (searchTerm.length > 0) {
            jsonview.traverse(tree, function(node) {
                if (node.el) {
                    const keyMatch = node.key != null && String(node.key).toLowerCase().includes(searchTerm);
                    const valueMatch = node.el.textContent.toLowerCase().includes(searchTerm);

                    if (keyMatch || valueMatch) {
                        for (let parent = node.parent; parent; parent = parent.parent) {
                            if (!parent.isExpanded) jsonview.toggleNode(parent);
                        }
                        node.el.classList.add('search-highlight');
                        searchResults.push(node.el);
                    }
                }
            });

            resultsCount.textContent = `${searchResults.length} ${T.matches}`;
            if (searchResults.length > 0) {
                currentSearchIndex = 0;
                searchResults[0].classList.add('search-current');
                searchResults[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        } else {
            resultsCount.textContent = '';
        }
    });

    // Add keyboard navigation for search results
    searchInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && searchResults.length > 0) {
            e.preventDefault();
            if (e.shiftKey) {
                // Previous result
                currentSearchIndex = currentSearchIndex > 0 ? currentSearchIndex - 1 : searchResults.length - 1;
            } else {
                // Next result
                currentSearchIndex = currentSearchIndex < searchResults.length - 1 ? currentSearchIndex + 1 : 0;
            }

            // Update highlighting
            searchResults.forEach(el => el.classList.remove('search-current'));
            searchResults[currentSearchIndex].classList.add('search-current');
            searchResults[currentSearchIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });

            resultsCount.textContent = `${currentSearchIndex + 1} ${T.of} ${searchResults.length} ${T.matches}`;
        }
    });

    // Add filter functionality
    const filterBtns = wrapper.querySelectorAll('.json-filters .btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            filterBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            const filter = this.dataset.filter;
            if (options.comparison) _hashSet('config', filter === 'differences' ? 'diff' : null);

            if (filter === 'differences') {
                jsonview.traverse(tree, node => {
                    if (node.el) node.el.style.display = node._configDifference ? '' : 'none';
                    if (node._configDifference && node.children.length && !node.isExpanded) jsonview.toggleNode(node);
                });
            } else if (filter === 'modified') {
                // Special handling for modified filter - show modified items and their children
                const modifiedNodes = [];

                // First, find all modified nodes
                jsonview.traverse(tree, function(node) {
                    if (node.el && node.el.classList.contains('modified-config')) {
                        modifiedNodes.push(node);
                    }
                });

                // Hide all nodes initially
                jsonview.traverse(tree, function(node) {
                    if (node.el) {
                        node.el.style.display = 'none';
                    }
                });

                // Show modified nodes and all their descendants
                modifiedNodes.forEach(modifiedNode => {
                    showNodeAndChildren(modifiedNode);
                });

            } else {
                // Standard filtering for other types
                const filterClass = {
                    numbers: 'json-type-number',
                    strings: 'json-type-string',
                    booleans: 'json-type-boolean',
                    objects: 'json-type-object',
                }[filter];
                jsonview.traverse(tree, function(node) {
                    if (node.el) {
                        const show = !filterClass || node.el.classList.contains(filterClass);
                        node.el.style.display = show ? '' : 'none';
                    }
                });
            }
        });
    });

    return tree;
}

function showNodeAndChildren(node) {
    if (node.el) {
        node.el.style.display = '';
    }
    if (node.children && node.children.length > 0) {
        node.children.forEach(child => {
            showNodeAndChildren(child);
        });
    }
}

function expandAllJson(selector) {
    const container = document.querySelector(selector);
    const tree = container._jsonTree;
    if (tree) {
        // Only expand visible nodes
        jsonview.traverse(tree, function(node) {
            if (node.el && node.el.style.display !== 'none' && node.children.length > 0 && !node.isExpanded) {
                jsonview.toggleNode(node);
            }
        });
    } else {
        console.log('Tree not found for selector:', selector);
    }
}

function collapseAllJson(selector) {
    const container = document.querySelector(selector);
    const tree = container._jsonTree;
    if (tree) {
        // Only collapse visible nodes
        jsonview.traverse(tree, function(node) {
            if (node.el && node.el.style.display !== 'none' && node.children.length > 0) {
                // Make sure it's collapsed
                if (node.isExpanded) {
                    jsonview.toggleNode(node);
                }
            }
        });
    } else {
        console.log('Tree not found for selector:', selector);
    }
}

// ---------------------------------------------------------------------------
// Combined protocol event log
// ---------------------------------------------------------------------------
function mergeEventLogs(before, after) {
    // Only normalize line endings and outer blank lines; indentation is meaningful.
    const lines = text => {
        const normalized = text.replace(/\r\n?/g, '\n').replace(/^\n+|\n+$/g, '');
        return normalized ? normalized.split('\n') : [];
    };
    const left = lines(before);
    const right = lines(after);
    if (!left.length || !right.length) return {before: left, after: right, overlap: 0};

    // Find the longest suffix of the before log matching the after log's prefix.
    // A linear prefix-function scan also handles repeated messages and ring-buffer truncation.
    const sequence = [...right, null, ...left];
    const prefix = new Array(sequence.length).fill(0);
    for (let i = 1; i < sequence.length; i++) {
        let j = prefix[i - 1];
        while (j > 0 && sequence[i] !== sequence[j]) j = prefix[j - 1];
        if (sequence[i] === sequence[j]) j++;
        prefix[i] = j;
    }
    let overlap = prefix[prefix.length - 1];
    if (!right.slice(0, overlap).some(line => line.trim())) overlap = 0;
    return {before: left, after: right.slice(overlap), overlap};
}

function initProtocolEventLog(data) {
    const container = document.getElementById('protocol-event-log');
    if (!container) return;
    const merged = mergeEventLogs(data.before_protocol_log, data.after_protocol_log);
    const sections = [];
    function section(label, lines, added = false) {
        sections.push({label, lines, added});
    }
    if (merged.before.length) section(T.tab_log_before, merged.before);
    if (merged.after.length) {
        if (merged.before.length && !merged.overlap) {
            sections.push({note: T.event_log_no_overlap});
        }
        section(merged.overlap ? T.event_log_added : T.tab_log_after, merged.after, merged.overlap > 0);
    } else {
        sections.push({note: merged.overlap ? T.event_log_no_new
            : merged.before.length ? T.event_log_no_after : T.event_log_empty});
    }
    initEventLogViewer(container, sections, [...merged.before, ...merged.after].join('\n'));
}

function initEventLogViewer(container, sections, copyText) {
    const viewer = container.closest('.event-log-viewer');
    const control = name => viewer.querySelector(`[data-log-${name}]`);
    const entries = [];
    const fragment = document.createDocumentFragment();
    for (const {label, lines = [], added, note} of sections) {
        const section = document.createElement('div');
        section.className = 'event-log-section' + (added ? ' protocol-log-added' : '');
        if (label || note) {
            const heading = document.createElement('div');
            heading.className = label ? 'event-log-heading' : 'event-log-note';
            heading.textContent = label || note;
            section.appendChild(heading);
        }
        for (const text of lines) {
            const row = document.createElement('div');
            row.className = 'event-log-line';
            const number = document.createElement('span');
            number.className = 'event-log-line-number';
            number.dataset.number = entries.length + 1;
            number.setAttribute('aria-hidden', 'true');
            const content = document.createElement('span');
            content.className = 'event-log-line-text';
            content.textContent = text;
            row.append(number, content);
            section.appendChild(row);
            entries.push({text, content});
        }
        fragment.appendChild(section);
    }
    container.replaceChildren(fragment);
    container.style.setProperty('--log-number-width', `${Math.max(3, String(entries.length).length) + 2}ch`);

    let matches = [];
    let matchedEntries = [];
    let current = -1;
    function selectMatch(index) {
        if (current >= 0) matches[current].classList.remove('is-current');
        current = matches.length ? (index + matches.length) % matches.length : -1;
        if (current >= 0) {
            const match = matches[current];
            match.classList.add('is-current');
            match.scrollIntoView({block: 'nearest', inline: 'nearest'});
        }
        control('matches').textContent = control('search').value
            ? T.event_log_matches.replace('${current}', current + 1).replace('${total}', matches.length) : '';
        control('prev').disabled = control('next').disabled = !matches.length;
    }
    control('search').oninput = () => {
        for (const entry of matchedEntries) entry.content.textContent = entry.text;
        matchedEntries = [];
        matches = [];
        current = -1;
        const query = control('search').value;
        if (query) {
            // A literal, case-insensitive search; match offsets refer to the original text.
            const pattern = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
            for (const entry of entries) {
                const hits = [...entry.text.matchAll(pattern)];
                if (!hits.length) continue;
                matchedEntries.push(entry);
                const parts = document.createDocumentFragment();
                let offset = 0;
                for (const hit of hits) {
                    parts.appendChild(document.createTextNode(entry.text.slice(offset, hit.index)));
                    const mark = document.createElement('mark');
                    mark.textContent = hit[0];
                    parts.appendChild(mark);
                    matches.push(mark);
                    offset = hit.index + hit[0].length;
                }
                parts.appendChild(document.createTextNode(entry.text.slice(offset)));
                entry.content.replaceChildren(parts);
            }
        }
        selectMatch(0);
    };
    control('search').onkeydown = event => {
        if (event.key === 'Enter') {
            event.preventDefault();
            selectMatch(current + (event.shiftKey ? -1 : 1));
        } else if (event.key === 'Escape') {
            control('search').value = '';
            control('search').oninput();
        }
    };
    control('prev').onclick = () => selectMatch(current - 1);
    control('next').onclick = () => selectMatch(current + 1);
    control('wrap').onchange = () => {
        container.classList.toggle('is-wrapped', control('wrap').checked);
        selectMatch(current);
    };
    control('copy').disabled = !copyText;
    control('copy-status').textContent = '';
    control('copy').onclick = async () => {
        try {
            await navigator.clipboard.writeText(copyText);
            control('copy-status').textContent = T.event_log_copied;
        } catch {
            control('copy-status').textContent = T.event_log_copy_failed;
        }
    };
    container.classList.toggle('is-wrapped', control('wrap').checked);
    control('search').oninput();
}

// ---------------------------------------------------------------------------
// Before/after configuration diff
// ---------------------------------------------------------------------------
function isInlineConfigArray(value) {
    return Array.isArray(value) && value.every(item => item === null || typeof item !== 'object');
}

function configDiff(before, after, inlineArrays = false) {
    const rows = [];
    const kind = value => value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
    function visit(left, right, path) {
        if (left === right) return;
        if (inlineArrays && isInlineConfigArray(left) && isInlineConfigArray(right)) {
            if (left.length !== right.length || left.some((value, index) => value !== right[index])) {
                rows.push({path, status: 'changed', before: left, after: right});
            }
            return;
        }
        const type = kind(left);
        if (type === kind(right) && (type === 'object' || type === 'array')) {
            const keys = [...new Set([...Object.keys(left), ...Object.keys(right)])];
            keys.sort(type === 'array' ? (a, b) => Number(a) - Number(b) : undefined);
            for (const key of keys) {
                // Bracket notation keeps API paths, dots and array indices unambiguous.
                const childPath = path + '[' + (type === 'array' ? key : JSON.stringify(key)) + ']';
                if (!Object.prototype.hasOwnProperty.call(left, key)) {
                    rows.push({path: childPath, status: 'added', after: right[key]});
                } else if (!Object.prototype.hasOwnProperty.call(right, key)) {
                    rows.push({path: childPath, status: 'removed', before: left[key]});
                } else {
                    visit(left[key], right[key], childPath);
                }
            }
        } else {
            rows.push({path, status: 'changed', before: left, after: right});
        }
    }
    visit(before, after, '$');
    return rows;
}

function configComparisonTree(before, after) {
    // Use the after snapshot as the main tree, retaining removed keys/array tails.
    // Define properties explicitly so keys such as __proto__ remain ordinary data.
    const object = value => value !== null && typeof value === 'object';
    if (isInlineConfigArray(before) && isInlineConfigArray(after)) return after;
    if (!object(before) || !object(after) || Array.isArray(before) !== Array.isArray(after)) return after;
    const merged = Array.isArray(after) ? [] : {};
    for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
        const inBefore = Object.prototype.hasOwnProperty.call(before, key);
        const inAfter = Object.prototype.hasOwnProperty.call(after, key);
        const value = !inAfter ? before[key] : !inBefore ? after[key] : configComparisonTree(before[key], after[key]);
        Object.defineProperty(merged, key, {value, enumerable: true, writable: true, configurable: true});
    }
    return merged;
}

function annotateConfigComparison(tree, rows) {
    const changes = new Map(rows.map(row => [row.path, row]));
    jsonview.traverse(tree, node => {
        if (!node.parent) node._configPath = '$';
        else node._configPath = node.parent._configPath + '[' + (Array.isArray(node.parent.value)
            ? node.key : JSON.stringify(String(node.key))) + ']';
        const change = changes.get(node._configPath);
        node._configChange = change;
        node._configInherited = node.parent?._configInherited || (change && change.status);
        if (!node.el || (!change && !node._configInherited)) return;
        for (let parent = node; parent; parent = parent.parent) parent._configDifference = true;
        node.el.classList.add('config-' + (change?.status || node._configInherited));
        if (!change) return;
        const badge = document.createElement('span');
        badge.className = 'config-change-label small';
        badge.textContent = T['config_diff_' + change.status];
        node.el.appendChild(badge);
    });
}

function layoutConfigTree(tree, content, options) {
    const comparison = Array.isArray(options.comparison);
    content.classList.add('config-tree-table');
    const header = document.createElement('div');
    header.className = 'config-table-header';
    const headings = comparison ? [T.config_field, T.snapshot_before, T.snapshot_after] : [T.config_field, T.value_col];
    headings.forEach((text, index) => {
        const cell = document.createElement('div');
        cell.textContent = text;
        if (!comparison && index === 1) cell.className = 'config-cell-shared';
        header.appendChild(cell);
    });
    content.prepend(header);

    function valueCell(node, value, present, label) {
        const cell = document.createElement('div');
        cell.className = 'config-table-value';
        cell.dataset.label = label;
        if (!present) {
            cell.classList.add('text-body-secondary');
            cell.textContent = T.config_diff_absent;
            return cell;
        }
        cell.textContent = JSON.stringify(value);
        // Resolve the before value independently: units/constants can differ from after.
        const resolved = options.apiConstants && _resolveFieldEntry(node, options.apiConstants);
        const field = resolved?.fieldEntry;
        if (field?.censored && value === null) {
            cell.textContent = `*${T.censored_value}*`;
        } else if (field && (value === null || typeof value !== 'object')) {
            const constant = field.constants?.find(c =>
                (c.version === -1 || options.hwVersion === -1 || (c.version & options.hwVersion) !== 0)
                && c.val === (typeof value === 'boolean' ? String(value) : value));
            if (constant) {
                const hint = document.createElement('span');
                hint.className = 'enum-hint';
                hint.textContent = ` (${constant.desc})`;
                cell.appendChild(hint);
            }
            if (field.unit) {
                const unit = document.createElement('span');
                unit.className = 'unit-hint';
                unit.textContent = ` ${field.unit.abbr}`;
                unit.title = field.unit.name;
                cell.appendChild(unit);
            }
        }
        return cell;
    }

    jsonview.traverse(tree, node => {
        if (!node.el) return;
        const row = node.el;
        row.classList.add('config-table-row');
        row.style.setProperty('--config-indent', row.style.marginLeft || '0px');
        const field = document.createElement('div');
        field.className = 'config-table-field';
        let value = row.querySelector('.json-value');
        let size = row.querySelector('.json-size');
        const inlineArray = isInlineConfigArray(node.value);
        if (inlineArray) {
            value?.remove();
            value = document.createElement('span');
            value.className = 'json-value config-inline-array';
            value.textContent = JSON.stringify(node.value);
            if (!size) {
                size = document.createElement('span');
                size.className = 'json-size';
            }
            size.textContent = `[${node.value.length}]`;
            const caret = row.querySelector('.caret-icon');
            if (caret) {
                const spacer = document.createElement('div');
                spacer.className = 'empty-icon';
                caret.replaceWith(spacer);
            }
        }
        // Move existing elements rather than rebuilding them, preserving caret/popover handlers.
        value?.remove();
        size?.remove();
        row.querySelector('.json-separator')?.remove();
        while (row.firstChild) field.appendChild(row.firstChild);
        row.appendChild(field);
        const status = node._configChange?.status || node._configInherited;
        const change = node._configChange;
        // Section sizes belong to the field name, not a separate value row on mobile.
        if (size && (inlineArray || (!status && !value))) field.appendChild(size);
        const current = value || (status ? size : null);
        const displayValue = (label, shared = false) => {
            const cell = document.createElement('div');
            cell.className = 'config-table-value' + (shared ? ' config-cell-shared' : '');
            cell.dataset.label = label;
            if (current) cell.appendChild(current);
            return cell;
        };
        if (!comparison || !status) {
            row.appendChild(displayValue(T.value_col, true));
        } else if (status === 'removed') {
            row.append(displayValue(T.snapshot_before), valueCell(node, null, false, T.snapshot_after));
        } else {
            row.appendChild(valueCell(node, change?.before,
                !!change && Object.prototype.hasOwnProperty.call(change, 'before'), T.snapshot_before));
            row.appendChild(displayValue(T.snapshot_after));
        }
    });
}

function initProtocolConfiguration(data) {
    const comparison = data.config_diff_available
        ? configDiff(data.before_protocol_json, data.after_protocol_json, true) : null;
    const source = Object.keys(data.after_protocol_json).length || !data.config_snapshots.includes('pre')
        ? data.after_protocol_json : data.before_protocol_json;
    const json = comparison ? configComparisonTree(data.before_protocol_json, data.after_protocol_json) : source;
    make_jsonview(json, '#protocol-json', {
        apiConstants: data.api_constants, hwVersion: _detectHwVersion(source), comparison, treeTable: true,
    });
    if (comparison) {
        const note = document.createElement('div');
        note.className = 'small text-body-secondary mb-2';
        note.textContent = T.config_diff_identical;
        if (!comparison.length) document.querySelector('#protocol-json .json-content').before(note);
        if (_hashParams().get('config') === 'diff') {
            document.querySelector('#protocol-json [data-filter="differences"]').click();
        }
    }
}

// ---------------------------------------------------------------------------
// Protocol Chart (unified single-page)
// ---------------------------------------------------------------------------
let protoChart = null;
let protoData = null;
let protoIsoTimes = [];
let protoIsoSelected = null;
let protoIsoHover = null;
let protoIsoSignature = '';
let protoStateLanes = [];
let protoStateSignature = '';

function initProtocolChart(data) {
    protoData = data;
    protoStateLanes = protoBuildStateLanes(data);
    protoStateSignature = '';
    initProtocolConfiguration(data);
    initProtocolEventLog(data);
    if (!protoData || !protoData.column_metadata) return;
    if (data.numeric_time_axis) {
        // Old links store sample indices in zx; new links store uptime in zms.
        const params = _hashParams();
        if (params.has('zx') && !params.has('zms')) {
            const bounds = params.get('zx').split(',').map(Number);
            if (bounds.length === 2 && bounds.every(Number.isFinite)) {
                _hashSet('zms', bounds.map(i => data.sample_times_ms[
                    Math.max(0, Math.min(data.sample_times_ms.length - 1, Math.round(i)))
                ]).join(','));
            }
        }
        _hashSet('zx', null);
    }

    // --- Backward compatibility: convert old ?configuration= or ?selected= to hash ---
    const urlParams = new URLSearchParams(window.location.search);
    const legacyCfg = data.legacy_config || urlParams.get('configuration') || '';
    const legacySel = data.legacy_selected || urlParams.get('selected') || '';
    if (legacyCfg || legacySel) {
        const cols = (legacyCfg || legacySel).split(',').filter(Boolean);
        if (cols.length > 0) {
            // Apply these as initial selection and put in hash
            const checkboxes = document.querySelectorAll('#proto-column-checkboxes input[type="checkbox"]');
            const colSet = new Set(cols);
            checkboxes.forEach(cb => {
                cb.checked = colSet.has(cb.dataset.column);
            });
            // If came from ?configuration=, also enable log axis (old default was log)
            if (legacyCfg) {
                const logCb = document.getElementById('proto-log-axis');
                if (logCb) logCb.checked = true;
            }
            // Migrate only legacy chart parameters; retain the report snapshot and tabs.
            const cleanUrl = new URL(window.location.href);
            cleanUrl.searchParams.delete('configuration');
            cleanUrl.searchParams.delete('selected');
            history.replaceState(null, '', cleanUrl.href);
            _protoUpdateHash();
        }
    } else {
        // Restore selection from URL hash if present
        const hashState = _protoParseHash();
        if (hashState.columns !== null) {
            const colSet = new Set(hashState.columns);
            const checkboxes = document.querySelectorAll('#proto-column-checkboxes input[type="checkbox"]');
            checkboxes.forEach(cb => {
                cb.checked = colSet.has(cb.dataset.column);
            });
            if (hashState.log) {
                const logCb = document.getElementById('proto-log-axis');
                if (logCb) logCb.checked = true;
            }
        }
    }

    initChartPicker('proto', data.column_metadata.map(col => col.name));
    // Render chart with initial selection
    protoRenderChart();
}

function _protoParseHash() {
    return _parseChartHash('cols', 'log');
}

function _protoUpdateHash() {
    _updateChartHash('#proto-column-checkboxes input[type="checkbox"]', 'proto-log-axis', 'cols', 'log');
}

function protoRenderChart() {
    if (!protoData) return;
    updateChartPicker('proto');

    // Gather selected columns
    const selected = [];
    document.querySelectorAll('#proto-column-checkboxes input[type="checkbox"]:checked').forEach(cb => {
        selected.push(cb.dataset.column);
    });

    // Build column label lookup from metadata
    const labelLookup = {};
    protoData.column_metadata.forEach((col, index) => {
        labelLookup[col.name] = {label: col.label, color: index};
    });

    // Log / linear Y-axis
    const logCheckbox = document.getElementById('proto-log-axis');
    const useLog = logCheckbox && logCheckbox.checked;

    // Build datasets
    const datasets = [];

    selected.forEach(colName => {
        const rawData = protoData.all_column_data[colName];
        if (!rawData) return;

        // For log view: replace 0 with 0.01 (Chart.js can't show 0 on log scale)
        // See https://github.com/chartjs/Chart.js/issues/9629
        const chartData = useLog ? rawData.map(v => (v === 0 ? 0.01 : v)) : rawData;

        const points = protoData.numeric_time_axis
            ? chartData.map((y, i) => ({x: protoData.sample_times_ms[i], y})) : chartData;
        const dataset = _chartDataset(labelLookup[colName].label, points, labelLookup[colName].color);
        dataset.signalKey = colName;
        if (useLog) dataset.inspectorValues = rawData;
        datasets.push(dataset);
    });

    protoChart = _createTimeSeriesChart({
        canvasId: 'proto-chart',
        pickerPrefix: 'proto',
        prevChart: protoChart,
        labels: protoData.labels,
        datasets: datasets,
        useLog: useLog,
        zoomXKey: protoData.numeric_time_axis ? 'zms' : 'zx',
        zoomYKey: 'zy',
        xScale: protoData.numeric_time_axis ? {
            type: 'linear', min: protoData.sample_times_ms[0],
            max: protoData.sample_times_ms[protoData.sample_times_ms.length - 1],
        } : undefined,
        xTickCallback: protoData.numeric_time_axis ? function(value, index, ticks) {
            return protoTimeTick(value, index, ticks, this.min, this.max);
        } : undefined,
        tooltipTitleCallback: protoData.numeric_time_axis
            ? items => items.length ? protoFormatTime(items[0].parsed.x) : '' : undefined,
        xTitle: protoData.numeric_time_axis
            ? (protoData.time_offset_ms === null ? T.protocol_uptime_axis : T.protocol_time_axis) : undefined,
        plugins: [protoStatePlugin, protoIsoPlugin],
    });

    // Persist selection in URL hash for sharing
    _protoUpdateHash();
}

function protoSelectAll(checked) {
    chartSelectAll('#proto-column-checkboxes input[type="checkbox"]', checked, protoRenderChart);
}

function protoResetZoom() {
    chartResetZoom(protoChart, protoData.numeric_time_axis ? 'zms' : 'zx', 'zy');
}

function protoTimeTick(value, index, ticks, min, max) {
    // Tick spacing, rather than recording duration, determines the precision
    // needed to distinguish adjacent labels after zooming or resizing.
    const spacing = ticks.reduce((smallest, tick, i) => i
        ? Math.min(smallest, Math.abs(tick.value - ticks[i - 1].value) || Infinity) : smallest, Infinity);
    const precise = spacing < 1000;
    const time = protoFormatTime(value, precise, false);
    // At sub-millisecond zoom the source clock cannot distinguish every tick.
    if (index && time === protoFormatTime(ticks[index - 1].value, precise, false)) return '';
    if (protoData.time_offset_ms !== null) {
        const date = ms => new Date(Math.round(ms + protoData.time_offset_ms)).toISOString().slice(0, 10);
        if (date(min) !== date(max)) return [time, date(value)];
    }
    return time;
}

function protoFormatTime(ms, precise = true, includeDate = true) {
    if (protoData.time_offset_ms !== null) {
        const timestamp = new Date(Math.round(ms + protoData.time_offset_ms)).toISOString();
        const samples = protoData.sample_times_ms || [];
        const day = value => Math.floor(Math.round(value + protoData.time_offset_ms) / 86400000);
        const showDate = includeDate && samples.length &&
            (day(samples[0]) !== day(samples[samples.length - 1]) || day(ms) !== day(samples[0]));
        return (showDate ? timestamp.slice(0, 10) + ' ' : '') + timestamp.slice(11, precise ? 23 : 19);
    }
    const value = Math.max(0, Math.round(ms));
    const hours = Math.floor(value / 3600000);
    const minutes = Math.floor(value / 60000) % 60;
    const seconds = Math.floor(value / 1000) % 60;
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}` +
        (precise ? `.${String(value % 1000).padStart(3, '0')}` : '');
}

// A sample's state holds until the next sample. Never extend beyond the recording.
function protoStateSegments(times, values) {
    const segments = [];
    for (let i = 0; i < times.length; i++) {
        const start = times[i];
        const end = i + 1 < times.length ? times[i + 1] : start;
        const value = Number.isInteger(values[i]) && values[i] >= 0 ? values[i] : null;
        const previous = segments[segments.length - 1];
        if (previous && previous.value === value && previous.end === start) previous.end = end;
        else segments.push({start, end, value});
    }
    return segments;
}

function protoBuildStateLanes(data) {
    const times = data.numeric_time_axis ? data.sample_times_ms : data.labels.map((_, i) => i);
    const hw = [data.report_json, data.after_protocol_json, data.before_protocol_json]
        .map(_detectHwVersion).find(version => version !== -1) ?? -1;
    return ['iec61851_state', 'charger_state', 'contactor_state', 'error_state', 'contactor_error']
        .filter(key => data.all_column_data[key]?.some(value => Number.isInteger(value) && value >= 0))
        .map(key => ({key, hw, segments: protoStateSegments(times, data.all_column_data[key])}));
}

function protoStateDescription(key, value, hw) {
    if (value === null) return {label: T.state_unknown, color: 'unknown'};
    if (key === 'iec61851_state' && value <= 4) {
        return {label: T['state_iec_' + value], color: ['idle', 'connected', 'charging', 'warning', 'error'][value]};
    }
    if (key === 'charger_state' && value <= 4) {
        return {label: T['state_charger_' + value], color: ['idle', 'warning', 'connected', 'charging', 'error'][value]};
    }
    if (key === 'error_state' || key === 'contactor_error') {
        return {label: value === 0 ? T.state_ok : `${T.state_error} ${value}`, color: value === 0 ? 'idle' : 'error'};
    }
    if (key === 'contactor_state') {
        if ((hw === 4 || hw === 32) && value <= 31) {
            const contacts = value & 3;
            const label = [T.state_open, 'L1+N', 'L2+L3', 'L1+N + L2+L3'][contacts];
            return {label: (value & 4) ? `${label} · ${T.state_error}` : label,
                color: (value & 4) ? 'error' : contacts ? 'charging' : 'idle'};
        }
        if ((hw === 1 || hw === 2) && value <= 3) {
            return {label: T['state_monitor_' + value], color: ['idle', 'connected', 'warning', 'charging'][value]};
        }
    }
    return {label: `${T.state_unknown} (${value})`, color: 'unknown'};
}

function protoStateLaneLabel(key) {
    return {
        iec61851_state: 'IEC 61851', charger_state: T.state_charger,
        contactor_state: T.state_contactor, error_state: T.state_error,
        contactor_error: T.chart_contactor_error,
    }[key];
}

const protoStatePlugin = {
    id: 'protoStateTimeline',
    afterDraw(chart) {
        const container = document.getElementById('proto-state-timeline');
        if (!container) return;
        container.classList.toggle('d-none', !protoStateLanes.length);
        if (!protoStateLanes.length) return;
        const scale = chart.scales.x;
        const {left, right} = chart.chartArea;
        const signature = [scale.min, scale.max, left, right].join(',');
        if (signature === protoStateSignature) return;
        protoStateSignature = signature;
        const lanes = document.getElementById('proto-state-lanes');
        const detail = document.getElementById('proto-state-detail');
        lanes.replaceChildren();
        detail.textContent = '';
        const formatTime = value => protoData.numeric_time_axis ? protoFormatTime(value)
            : protoData.labels[value] ?? String(value);
        for (const lane of protoStateLanes) {
            const row = document.createElement('div');
            row.className = 'proto-state-lane';
            row.style.marginLeft = left + 'px';
            row.style.width = Math.max(0, right - left) + 'px';
            const name = document.createElement('div');
            name.className = 'proto-state-name';
            name.textContent = protoStateLaneLabel(lane.key);
            const track = document.createElement('div');
            track.className = 'proto-state-track';
            row.append(name, track);
            lanes.appendChild(row);
            for (const segment of lane.segments) {
                if (segment.end < scale.min || segment.start > scale.max) continue;
                const start = Math.max(left, scale.getPixelForValue(segment.start));
                const end = Math.min(right, scale.getPixelForValue(segment.end));
                if (end < start) continue;
                const {label, color} = protoStateDescription(lane.key, segment.value, lane.hw);
                const band = document.createElement('button');
                band.type = 'button';
                band.className = 'proto-state-band state-' + color;
                const width = Math.max(1, end - start);
                band.style.left = Math.min(start - left, Math.max(0, right - left - width)) + 'px';
                band.style.width = width + 'px';
                if (width > 35) band.textContent = label;
                const duration = protoData.numeric_time_axis ? ` · ${((segment.end - segment.start) / 1000).toFixed(3)} s` : '';
                band.title = `${name.textContent}: ${label} · ${formatTime(segment.start)} – ${formatTime(segment.end)}${duration}`;
                if (segment.value !== null) band.title += ` · ${lane.key}=${segment.value}`;
                band.setAttribute('aria-label', band.title);
                const show = () => { detail.textContent = band.title; };
                band.addEventListener('mouseenter', show);
                band.addEventListener('focus', show);
                band.addEventListener('click', show);
                track.appendChild(band);
            }
        }
    },
};

const protoIsoPlugin = {
    id: 'protoIsoTimeline',
    afterDraw(chart) {
        protoIsoRender(chart);
        const index = protoIsoHover ?? protoIsoSelected;
        if (index === null || !protoData.iso15118_correlation_available) return;
        const time = protoIsoTimes[index];
        const scale = chart.scales.x;
        if (time < scale.min || time > scale.max || !Number.isFinite(time)) return;
        const x = scale.getPixelForValue(time);
        const ctx = chart.ctx;
        ctx.save();
        ctx.strokeStyle = document.documentElement.getAttribute('data-bs-theme') === 'dark' ? '#f0f0f0' : '#212529';
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(x, chart.chartArea.top);
        ctx.lineTo(x, chart.chartArea.bottom);
        ctx.stroke();
        ctx.restore();
    },
};

function protoIsoLane(protocol) {
    if (protocol.startsWith('HomePlug')) return 0;
    if (protocol === 'TCP' || /^(TLS|SSL)/.test(protocol)) return 1;
    if (/^(V2G|ISO.?15118|DIN)/i.test(protocol)) return 2;
    return 3;
}

// Cluster in screen space: packet ordering and timing remain untouched.
function protoIsoClusters(times, packets, min, max, width) {
    const clusters = [];
    const lastByLane = [];
    times.forEach((time, index) => {
        if (time < min || time > max) return;
        const lane = protoIsoLane(packets[index][4]);
        const pixel = (time - min) / (max - min || 1) * width;
        let cluster = lastByLane[lane];
        // Leave room for count labels even when packets straddle a bin edge.
        if (!cluster || pixel - cluster.pixel >= 34) {
            cluster = {lane, pixel, indices: []};
            lastByLane[lane] = cluster;
            clusters.push(cluster);
        }
        cluster.indices.push(index);
    });
    return clusters;
}

function protoIsoRender(chart) {
    const lanes = document.getElementById('proto-iso-lanes');
    if (!lanes || !iso15118Packets) return;
    const status = document.getElementById('proto-iso-status');
    if (!protoData.iso15118_correlation_available) {
        lanes.replaceChildren();
        status.textContent = T.iso15118_clock_invalid;
        return;
    }
    const {min, max} = chart.scales.x;
    const {left, right} = chart.chartArea;
    const signature = [min, max, left, right, iso15118Packets.length, protoIsoSelected].join(',');
    if (signature === protoIsoSignature) return;
    protoIsoSignature = signature;
    lanes.replaceChildren();
    const rows = ['SLAC / HomePlug', 'TCP / TLS', 'V2G', T.iso15118_other].map(label => {
        const row = document.createElement('div');
        row.className = 'proto-iso-lane';
        row.style.marginLeft = left + 'px';
        row.style.width = Math.max(0, right - left) + 'px';
        const name = document.createElement('span');
        name.className = 'proto-iso-lane-label';
        name.textContent = label;
        row.appendChild(name);
        lanes.appendChild(row);
        return row;
    });
    const clusters = protoIsoClusters(protoIsoTimes, iso15118Packets, min, max, right - left);
    let visible = 0;
    clusters.forEach(({lane, pixel, indices}) => {
        visible += indices.length;
        const index = indices[0];
        const packet = iso15118Packets[index];
        const button = document.createElement('button');
        button.className = 'proto-iso-marker ' + iso15118ProtoClass(packet[4]);
        if (indices.includes(protoIsoSelected)) button.classList.add('proto-iso-active');
        button.style.left = pixel + 'px';
        button.textContent = indices.length > 1 ? String(indices.length) : '•';
        button.title = indices.length > 1
            ? `${indices.length} ${T.iso15118_packets}: ${protoFormatTime(protoIsoTimes[index])} – ${protoFormatTime(protoIsoTimes[indices[indices.length - 1]])}`
            : `#${packet[0]} · ${protoFormatTime(protoIsoTimes[index])} · ${packet[4]} · ${packet[6]}`;
        button.setAttribute('aria-label', button.title);
        button.addEventListener('click', () => protoIsoOpen(indices));
        button.addEventListener('mouseenter', () => { protoIsoHover = index; chart.draw(); });
        button.addEventListener('mouseleave', () => { protoIsoHover = null; chart.draw(); });
        rows[lane].appendChild(button);
    });
    const range = protoIsoTimes.length ? T.iso15118_range
        .replace('${start}', protoFormatTime(protoIsoTimes[0]))
        .replace('${end}', protoFormatTime(protoIsoTimes[protoIsoTimes.length - 1])) : '';
    status.textContent = [range, T.iso15118_visible.replace('${visible}', visible).replace('${total}', protoIsoTimes.length)]
        .filter(Boolean).join(' · ');
}

function protoIsoFit() {
    if (!protoChart || !protoIsoTimes.length || !protoData.iso15118_correlation_available) return;
    const samples = protoData.sample_times_ms;
    const min = Math.min(samples[0], protoIsoTimes[0]);
    const max = Math.max(samples[samples.length - 1], protoIsoTimes[protoIsoTimes.length - 1]);
    protoChart.zoomScale('x', {min, max}, 'none');
    _saveZoomToHash(protoChart, 'zms', 'zy');
}

function protoIsoOpen(indices) {
    const select = document.getElementById('proto-iso-packets');
    select.replaceChildren();
    indices.forEach(index => {
        const pkt = iso15118Packets[index];
        const option = document.createElement('option');
        option.value = index;
        option.textContent = `#${pkt[0]} · ${protoFormatTime(protoIsoTimes[index])} · ${pkt[4]} · ${pkt[6]}`;
        select.appendChild(option);
    });
    document.getElementById('proto-iso-detail').classList.remove('d-none');
    protoIsoSelect(indices[0]);
}

function protoIsoSelect(index) {
    protoIsoSelected = index;
    protoIsoHover = null;
    const pkt = iso15118Packets[index];
    document.getElementById('proto-iso-summary').textContent =
        `#${pkt[0]} · ${protoFormatTime(protoIsoTimes[index])} · ${pkt[2]} → ${pkt[3]} · ${pkt[4]} · ${pkt[6]}`;
    document.getElementById('proto-iso-tree').replaceChildren(renderIso15118Tree(pkt[7], true, false));
    protoChart.draw();
}

function protoIsoClear() {
    protoIsoSelected = null;
    protoIsoHover = null;
    document.getElementById('proto-iso-detail').classList.add('d-none');
    protoChart.draw();
}

function protoIsoShowPacket(index) {
    bootstrap.Tab.getOrCreateInstance(document.getElementById('chart-tab')).show();
    const time = protoIsoTimes[index];
    if (time < protoChart.scales.x.min || time > protoChart.scales.x.max) {
        protoChart.zoomScale('x', {min: Math.max(0, time - 5000), max: time + 5000}, 'none');
        _saveZoomToHash(protoChart, 'zms', 'zy');
    }
    protoIsoOpen([index]);
    document.getElementById('proto-iso-detail').scrollIntoView({block: 'nearest'});
}

function vislog_report(data) {
    const hwVersion = _detectHwVersion(data.report_json);
    const jsonviewOpts = {
        apiConstants: data.api_constants, hwVersion, treeTable: true,
    };
    if (document.getElementById('report-json')) make_jsonview(data.report_json, '#report-json', jsonviewOpts);

    const reportLog = document.getElementById('report-log-text');
    if (reportLog) {
        const text = data.report_log || '';
        initEventLogViewer(reportLog, text ? [{lines: text.replace(/\r\n?/g, '\n').split('\n')}]
            : [{note: T.event_log_empty}], text);
    }

    initReportFeatures(data);
}

function renderReportCharts() {
    if (cmData) renderCmChart();
    if (metersData) renderMetersCharts();
}

function initReportFeatures(data) {
    // Only set trace text if the element exists (might not if no remaining trace content)
    const traceText = document.getElementById('report-trace-text');
    if (traceText) {
        traceText.value = data.report_trace;
    }

    // Populate module trace textareas (filled via JS to avoid HTML injection in <textarea>)
    if (data.trace_modules) {
        for (const [moduleName, moduleContent] of Object.entries(data.trace_modules)) {
            const el = document.getElementById('trace-' + moduleName + '-text');
            if (el) {
                el.value = moduleContent;
            }
        }
    }

    // Initialize the Wireshark-style iso15118_ll packet list (lazy fetch)
    if (data.iso15118_ll_available) {
        initIso15118PacketList(data.has_embedded_reports ? data.snapshot : null);
    }

    // Initialize charge manager chart if parsed data is available
    if (data.cm_parsed) {
        initCmChart(data.cm_parsed);
    }

    // Initialize meters history/live charts if parsed data is available
    if (data.meters_parsed) {
        initMetersCharts(data.meters_parsed);
    }

    // Coredump is now rendered server-side, no JS needed
}

// ---------------------------------------------------------------------------
// ISO 15118 low-level trace: Wireshark-style packet list
// ---------------------------------------------------------------------------
// Packet format (from /<lang>/<uuid>/iso15118.json):
//   [number, epoch_time, src, dst, protocol, length, info, tree]
// where tree is a nested list of Wireshark detail labels:
//   node := "leaf label" | [label, [node, ...]]
let iso15118Packets = null;
let iso15118HasBootEpoch = false;
let iso15118TzOffset = 0;  // charger's UTC offset in seconds
let iso15118SelectedRow = null;
let iso15118DetailRow = null;

function initIso15118PacketList(snapshot) {
    const statusEl = document.getElementById('iso15118-status');
    const listEl = document.getElementById('iso15118-packet-list');
    if (!statusEl || !listEl) return;

    let url = location.pathname.replace(/\/+$/, '') + '/iso15118.json';
    if (snapshot) url += '?snapshot=' + encodeURIComponent(snapshot);
    fetch(url)
        .then(r => {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(d => {
            iso15118Packets = d.packets;
            iso15118HasBootEpoch = d.has_boot_epoch;
            iso15118TzOffset = d.tz_offset || 0;
            if (protoData) {
                // Subtract the exact millisecond offset used by the pcap writer.
                protoIsoTimes = d.packets.map(pkt => Math.round(pkt[1] * 1000) - d.boot_epoch_ms);
                if (protoIsoTimes.some(t => !Number.isFinite(t) || t < 0) ||
                    protoIsoTimes.some((t, i) => i > 0 && t < protoIsoTimes[i - 1])) {
                    protoData.iso15118_correlation_available = false;
                }
                document.getElementById('proto-iso-fit').disabled = !protoData.iso15118_correlation_available || !protoIsoTimes.length;
                protoChart.draw();
            }
            statusEl.classList.add('d-none');
            listEl.classList.remove('d-none');

            const filterEl = document.getElementById('iso15118-filter');
            filterEl.disabled = false;
            filterEl.addEventListener('input', () => renderIso15118Rows(filterEl.value));

            document.getElementById('iso15118-tbody').addEventListener('click', ev => {
                const row = ev.target.closest('tr[data-idx]');
                if (row) toggleIso15118Detail(row);
            });
            document.getElementById('iso15118-tbody').addEventListener('keydown', ev => {
                if (ev.target.matches('tr[data-idx]') && (ev.key === 'Enter' || ev.key === ' ')) {
                    ev.preventDefault();
                    toggleIso15118Detail(ev.target);
                }
            });
            window.matchMedia('(min-width: 1200px)').addEventListener('change', placeIso15118Detail);

            renderIso15118Rows('');
        })
        .catch(e => {
            console.error('iso15118 packet list failed:', e);
            statusEl.textContent = T.iso15118_load_failed;
            const timelineStatus = document.getElementById('proto-iso-status');
            if (timelineStatus) timelineStatus.textContent = T.iso15118_load_failed;
        });
}

function iso15118FormatTime(epoch) {
    if (iso15118HasBootEpoch) {
        // Absolute time in the charger's timezone (matching the trace/event
        // log timestamps, which are in local time). Falls back to UTC if the
        // charger's timezone is unknown (tz_offset = 0).
        return new Date((epoch + iso15118TzOffset) * 1000).toISOString().substring(11, 23);
    }
    // No RTC reference: epoch equals the uptime
    const ms = Math.round(epoch * 1000);
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    const s = Math.floor((ms % 60000) / 1000);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:` +
           `${String(s).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
}

function iso15118ProtoClass(proto) {
    if (proto.startsWith('HomePlug')) return 'iso15118-proto-hpav';
    if (proto.startsWith('V2G')) return 'iso15118-proto-v2g';
    if (proto.startsWith('TLS') || proto.startsWith('SSL')) return 'iso15118-proto-tls';
    if (proto === 'ICMPv6') return 'iso15118-proto-icmpv6';
    if (proto === 'TCP') return 'iso15118-proto-tcp';
    if (proto === 'UDP' || proto === 'MDNS' || proto === 'DHCPv6') return 'iso15118-proto-udp';
    return '';
}

function renderIso15118Rows(filter) {
    const tbody = document.getElementById('iso15118-tbody');
    clearIso15118Detail();
    tbody.textContent = '';

    const needle = filter.trim().toLowerCase();
    const frag = document.createDocumentFragment();
    let shown = 0;

    iso15118Packets.forEach((pkt, idx) => {
        const [no, epoch, src, dst, proto, len, info] = pkt;
        if (needle) {
            const haystack = `${no} ${src} ${dst} ${proto} ${info}`.toLowerCase();
            if (!haystack.includes(needle)) return;
        }
        shown++;

        const row = document.createElement('tr');
        row.dataset.idx = idx;
        row.tabIndex = 0;
        row.setAttribute('aria-expanded', 'false');
        row.setAttribute('aria-controls', 'iso15118-detail');
        const cls = iso15118ProtoClass(proto);
        if (cls) row.className = cls;

        for (const [text, tdCls] of [[no, 'iso15118-col-no'], [iso15118FormatTime(epoch), 'iso15118-col-time'],
                                     [src, 'iso15118-col-addr'], [dst, 'iso15118-col-addr'],
                                     [proto, 'iso15118-col-proto'], [len, 'iso15118-col-len'],
                                     [info, 'iso15118-col-info']]) {
            const td = document.createElement('td');
            td.className = tdCls;
            td.textContent = text;
            td.title = text;
            row.appendChild(td);
        }
        frag.appendChild(row);
    });

    tbody.appendChild(frag);

    const countEl = document.getElementById('iso15118-count');
    countEl.textContent = needle
        ? `${shown} / ${iso15118Packets.length}`
        : `${iso15118Packets.length}`;
}

function clearIso15118Detail(restoreFocus = false) {
    const detail = document.getElementById('iso15118-detail');
    detail.classList.add('d-none');
    document.getElementById('iso15118-detail-host').appendChild(detail);
    document.getElementById('iso15118-workspace').classList.remove('has-selection');
    if (iso15118DetailRow) {
        iso15118DetailRow.remove();
        iso15118DetailRow = null;
    }
    if (iso15118SelectedRow) {
        iso15118SelectedRow.classList.remove('iso15118-selected');
        iso15118SelectedRow.setAttribute('aria-expanded', 'false');
        if (restoreFocus) iso15118SelectedRow.focus({preventScroll: true});
        iso15118SelectedRow = null;
    }
}

function placeIso15118Detail() {
    if (!iso15118SelectedRow) return;
    const detail = document.getElementById('iso15118-detail');
    // Move the same tree between panes so expanded fields survive resizing.
    if (window.matchMedia('(min-width: 1200px)').matches) {
        document.getElementById('iso15118-detail-host').appendChild(detail);
        if (iso15118DetailRow) iso15118DetailRow.remove();
        iso15118DetailRow = null;
    } else {
        if (!iso15118DetailRow) {
            iso15118DetailRow = document.createElement('tr');
            iso15118DetailRow.className = 'iso15118-detail-row';
            const td = document.createElement('td');
            td.colSpan = 7;
            iso15118DetailRow.appendChild(td);
            iso15118SelectedRow.after(iso15118DetailRow);
        }
        iso15118DetailRow.firstElementChild.appendChild(detail);
    }
}

function toggleIso15118Detail(row) {
    const wasSelected = (iso15118SelectedRow === row);
    clearIso15118Detail();
    if (wasSelected) return;  // second click on the same row just collapses

    const index = Number(row.dataset.idx);
    const pkt = iso15118Packets[index];
    document.getElementById('iso15118-detail-title').textContent =
        `${T.iso15118_col_no} ${pkt[0]} · ${pkt[4]} · ${iso15118FormatTime(pkt[1])}`;
    document.getElementById('iso15118-detail-summary').textContent = pkt[6];
    const button = document.getElementById('iso15118-detail-chart');
    button.classList.toggle('d-none', !(protoData && protoData.iso15118_correlation_available));
    button.onclick = () => protoIsoShowPacket(index);
    const body = document.getElementById('iso15118-detail-body');
    body.replaceChildren(renderIso15118Tree(pkt[7], true, false));

    row.classList.add('iso15118-selected');
    row.setAttribute('aria-expanded', 'true');
    iso15118SelectedRow = row;
    document.getElementById('iso15118-workspace').classList.add('has-selection');
    document.getElementById('iso15118-detail').classList.remove('d-none');
    placeIso15118Detail();
    body.scrollTop = 0;
}

function renderIso15118Tree(nodes, topLevel, openAll) {
    const container = document.createElement('div');
    container.className = 'iso15118-tree';

    nodes.forEach((node, idx) => {
        if (Array.isArray(node)) {
            const details = document.createElement('details');
            // Expand the topmost protocol layer (usually the interesting
            // one: V2G Message, HomePlug AV, ...) including all subtrees
            const open = openAll || (topLevel && idx === nodes.length - 1);
            if (open) details.open = true;
            const summary = document.createElement('summary');
            summary.textContent = node[0];
            details.appendChild(summary);
            details.appendChild(renderIso15118Tree(node[1], false, open));
            container.appendChild(details);
        } else {
            const leaf = document.createElement('div');
            leaf.className = 'iso15118-leaf';
            leaf.textContent = node;
            container.appendChild(leaf);
        }
    });

    return container;
}


// ---------------------------------------------------------------------------
// Charge Manager Chart
// ---------------------------------------------------------------------------
let cmChart = null;
let cmData = null;

function initCmChart(data) {
    cmData = data;
    if (!cmData || !cmData.columns) return;

    const container = document.getElementById('cm-column-groups');
    if (!container) return;

    // Group columns
    const groups = {};
    cmData.columns.forEach(col => {
        if (!groups[col.group]) groups[col.group] = [];
        groups[col.group].push(col);
    });

    // Default selected: PV group key columns + summary/allocation overview.
    // pm_bat only exists in newer traces; missing keys are simply ignored.
    const defaultKeys = new Set(['pm_mtr', 'pm_bat', 'pm_avl', 'pv_raw', 's0_raw_total', 's9_raw_total', 'alloc_current']);

    // Restore selection from URL hash if present
    const hashState = _cmParseHash();
    const restoredKeys = hashState.columns;
    const restoredLog = hashState.log;
    const useRestored = restoredKeys !== null;
    const selectedKeys = useRestored ? new Set(restoredKeys) : defaultKeys;

    container.innerHTML = '';
    for (const [groupName, cols] of Object.entries(groups)) {
        const groupDiv = document.createElement('div');
        groupDiv.className = 'chart-column-group';
        const heading = document.createElement('h6');
        heading.textContent = groupName;
        const groupDesc = _cmGroupDesc(groupName);
        if (groupDesc) heading.appendChild(_cmInfoBtn(groupDesc));
        groupDiv.appendChild(heading);

        cols.forEach(col => {
            const label = document.createElement('label');
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.dataset.column = col.key;
            cb.defaultChecked = defaultKeys.has(col.key);
            cb.checked = selectedKeys.has(col.key);
            cb.addEventListener('change', renderCmChart);
            label.appendChild(cb);
            label.appendChild(document.createTextNode(' ' + col.label));
            const desc = _cmColumnDesc(col.key);
            if (desc) label.appendChild(_cmInfoBtn(desc));
            groupDiv.appendChild(label);
        });

        container.appendChild(groupDiv);
    }

    // Restore log axis state
    if (restoredLog) {
        const logCb = document.getElementById('cm-log-axis');
        if (logCb) logCb.checked = true;
    }

    initChartPicker('cm', cmData.columns.map(col => col.key));
    // Auto-render with defaults/restored state
    renderCmChart();
}

// Create a clickable (i) info button that shows the given description in a
// popover. Same pattern as the JSON viewer field info buttons.
function _cmInfoBtn(desc) {
    const btn = document.createElement('i');
    btn.className = 'bi bi-info-circle cm-info-btn';
    btn.setAttribute('tabindex', '0');
    btn.setAttribute('role', 'button');
    // Prevent toggling the surrounding label's checkbox when clicking the icon
    btn.addEventListener('click', e => e.preventDefault());

    new bootstrap.Popover(btn, {
        content: desc,
        placement: 'right',
        trigger: 'focus',
        fallbackPlacements: ['right', 'left', 'top', 'bottom'],
        customClass: 'field-info-popover',
    });
    return btn;
}

// Help text for a column group heading (from i18n dict T).
function _cmGroupDesc(groupName) {
    if (groupName === 'PV') return T.cm_group_desc_pv;
    if (/^L[123]$/.test(groupName)) return T.cm_group_desc_lx;
    if (groupName === 'Step 0') return T.cm_group_desc_s0;
    if (groupName === 'Step 9') return T.cm_group_desc_s9;
    if (groupName === 'Allocation') return T.cm_group_desc_alloc;
    return null;
}

// Help text for a single column (from i18n dict T). The three phase groups
// L1-L3 share their descriptions via the lx_ prefix; the summary columns of
// step 0 and step 9 share theirs via the sx_ prefix and _lx suffix.
function _cmColumnDesc(key) {
    const normalized = key
        .replace(/^l[123]_/, 'lx_')
        .replace(/^s[09]_/, 'sx_')
        .replace(/_L[123]$/, '_lx');
    return T['cm_desc_' + normalized] || null;
}

function _cmParseHash() {
    return _parseChartHash('cm', 'cmlog');
}

function _cmUpdateHash() {
    _updateChartHash('#cm-column-groups input[type="checkbox"]', 'cm-log-axis', 'cm', 'cmlog');
}

function cmSelectAll(checked) {
    chartSelectAll('#cm-column-groups input[type="checkbox"]', checked, renderCmChart);
}

function cmResetZoom() {
    chartResetZoom(cmChart, 'cmzx', 'cmzy');
}

function renderCmChart() {
    if (!cmData) return;
    updateChartPicker('cm');

    // Gather selected columns
    const selected = [];
    document.querySelectorAll('#cm-column-groups input[type="checkbox"]:checked').forEach(cb => {
        selected.push(cb.dataset.column);
    });

    // Build timestamp lookup: sorted array of [row_idx, timestamp_string]
    // for nearest-match lookups on the x-axis
    const tsEntries = cmData.timestamps || [];
    const tsMap = {};
    tsEntries.forEach(([idx, ts]) => { tsMap[idx] = ts; });

    // Find the nearest timestamp for a given row index
    function nearestTimestamp(rowIdx) {
        if (tsEntries.length === 0) return null;
        // Binary search for closest entry
        let lo = 0, hi = tsEntries.length - 1;
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (tsEntries[mid][0] < rowIdx) lo = mid + 1;
            else hi = mid;
        }
        // lo is the first entry >= rowIdx; compare with lo-1
        if (lo > 0 && (lo >= tsEntries.length ||
            Math.abs(tsEntries[lo - 1][0] - rowIdx) <= Math.abs(tsEntries[lo][0] - rowIdx))) {
            lo = lo - 1;
        }
        return tsEntries[lo][1];
    }

    // Build x-axis labels (row indices)
    const labels = [];
    for (let i = 0; i < cmData.row_count; i++) {
        labels.push(i);
    }

    // Build datasets
    const datasets = [];
    const colLookup = {};
    cmData.columns.forEach((c, index) => { colLookup[c.key] = {...c, color: index}; });

    selected.forEach(key => {
        const colMeta = colLookup[key];
        if (!colMeta) return;

        let data;
        if (cmData.table_data && cmData.table_data[key]) {
            // Dense table data, use directly as array
            data = cmData.table_data[key];
        } else if (cmData.summary_data && cmData.summary_data[key]) {
            // Sparse summary data, convert to {x, y} points
            data = cmData.summary_data[key].map(([idx, val]) => ({ x: idx, y: val }));
        } else {
            return;
        }

        const dataset = _chartDataset(colMeta.label, data, colMeta.color);
        dataset.signalKey = key;
        datasets.push(dataset);
    });

    // Log / linear Y-axis
    const logCheckbox = document.getElementById('cm-log-axis');
    const useLog = logCheckbox && logCheckbox.checked;

    cmChart = _createTimeSeriesChart({
        canvasId: 'cm-chart',
        pickerPrefix: 'cm',
        prevChart: cmChart,
        labels: labels,
        datasets: datasets,
        useLog: useLog,
        xMaxTicksLimit: 10,
        zoomXKey: 'cmzx',
        zoomYKey: 'cmzy',
        xTickCallback: function(value) {
            const ts = nearestTimestamp(value);
            if (ts) return ts.split(' ')[1] || ts;
            return '';
        },
        tooltipTitleCallback: function(items) {
            if (!items.length) return '';
            const idx = items[0].parsed.x;
            const ts = tsMap[idx] || nearestTimestamp(idx);
            return ts ? `Row ${idx} - ${ts}` : `Row ${idx}`;
        },
    });

    // Persist selection in URL hash for sharing
    _cmUpdateHash();
}

// ---------------------------------------------------------------------------
// Meters History/Live Charts
// ---------------------------------------------------------------------------
let metersData = null;
let metersHistoryChart = null;
let metersLiveChart = null;

function initMetersCharts(data) {
    metersData = data;
    if (!metersData) return;
    renderMetersCharts();
}

// History has a fixed sample rate: 720 samples over 48 hours = 4 minutes.
const METERS_HISTORY_INTERVAL_S = 240;
// Live sampling approaches 2 Hz; used only if samples_per_second is missing.
const METERS_LIVE_FALLBACK_SPS = 2;

function renderMetersCharts() {
    if (!metersData) return;

    if (metersData.history) {
        metersHistoryChart = _renderMetersChart({
            canvasId: 'meters-history-chart',
            prevChart: metersHistoryChart,
            section: metersData.history,
            intervalSeconds: METERS_HISTORY_INTERVAL_S,
            reportTime: metersData.report_time,
            tzOffset: metersData.tz_offset,
            zoomXKey: 'mhzx',
            zoomYKey: 'mhzy',
        });
    }

    if (metersData.live) {
        const sps = metersData.live.samples_per_second;
        metersLiveChart = _renderMetersChart({
            canvasId: 'meters-live-chart',
            prevChart: metersLiveChart,
            section: metersData.live,
            intervalSeconds: 1 / (sps > 0 ? sps : METERS_LIVE_FALLBACK_SPS),
            reportTime: metersData.report_time,
            tzOffset: metersData.tz_offset,
            zoomXKey: 'mlzx',
            zoomYKey: 'mlzy',
        });
    }
}

// Format relative seconds as "[-]H:MM:SS" / "[-]M:SS".
function _formatMetersRelTime(seconds, withDecimals) {
    const sign = seconds < 0 ? '-' : '';
    let s = Math.abs(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = withDecimals ? (s % 60).toFixed(1) : String(Math.floor(s % 60));
    const pad = v => String(v).padStart(2, '0');
    const padSec = sec.length < (withDecimals ? 4 : 2) ? '0' + sec : sec;
    if (h > 0) return `${sign}${h}:${pad(m)}:${padSec}`;
    return `${sign}${m}:${padSec}`;
}

// Format an epoch as "HH:MM:SS" (withDate: "DD.MM. HH:MM:SS"). The epoch is
// expected to be pre-shifted into the desired timezone (UTC getters).
function _formatMetersAbsTime(epochSeconds, withDate, withDecimals) {
    const d = new Date(epochSeconds * 1000);
    const pad = v => String(v).padStart(2, '0');
    let s = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
    if (withDecimals) s += '.' + Math.floor(d.getUTCMilliseconds() / 100);
    if (withDate) s = `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}. ${s}`;
    return s;
}

function _renderMetersChart(cfg) {
    const slots = cfg.section.slots;
    // All slot sample arrays have the same length; use the longest to be safe
    const totalCount = Math.max(...slots.map(s => s.samples.length));

    // Trim leading samples where no slot has seen a value yet, so the chart
    // starts at the first available data point.
    let firstIdx = 0;
    while (firstIdx < totalCount &&
           !slots.some(s => s.samples[firstIdx] != null)) {
        firstIdx++;
    }
    if (firstIdx >= totalCount) firstIdx = 0;  // all samples null
    const sampleCount = totalCount - firstIdx;

    // Age of the i-th (trimmed) sample relative to report creation: the
    // newest (last) sample is 'offset' ms old, earlier samples are one
    // interval apart each.
    const offsetSeconds = (cfg.section.offset || 0) / 1000;
    const sampleAge = i =>
        offsetSeconds + (sampleCount - 1 - i) * cfg.intervalSeconds;

    // With a valid report creation time (from rtc/time, UTC) the x-axis
    // shows absolute times in the charger's timezone (matching the local-time
    // event log; UTC fallback if the timezone is unknown); otherwise negative
    // time before the report.
    const absolute = cfg.reportTime != null;
    // Charger's UTC offset; null/undefined means unknown -> display UTC
    const tzKnown = cfg.tzOffset != null;
    const tzOffset = tzKnown ? cfg.tzOffset : 0;
    // Include the date in absolute tick labels if the data spans > 24h
    const withDate = sampleCount * cfg.intervalSeconds > 24 * 3600;
    // Sub-minute sample spacing (live data): show tooltip time with decimals
    const withDecimals = cfg.intervalSeconds < 60;

    const formatTime = (i, decimals) => absolute
        ? _formatMetersAbsTime(cfg.reportTime + tzOffset - sampleAge(i), withDate, decimals)
        : _formatMetersRelTime(-sampleAge(i), decimals);

    const labels = [];
    for (let i = 0; i < sampleCount; i++) {
        labels.push(i);
    }

    const datasets = slots.map((slot, idx) => {
        const ds = _chartDataset(slot.name, slot.samples.slice(firstIdx), idx);
        ds.inspectorUnit = 'W';
        // Sample arrays may be mostly null (no value seen yet); draw small
        // points so isolated values are visible despite the line gaps.
        ds.pointRadius = 1.5;
        ds.spanGaps = false;
        return ds;
    });

    return _createTimeSeriesChart({
        canvasId: cfg.canvasId,
        prevChart: cfg.prevChart,
        labels: labels,
        datasets: datasets,
        useLog: false,
        xMaxTicksLimit: 15,
        xTitle: absolute
            ? (tzKnown ? (T.meters_time_axis_local || 'Time (local)')
                       : (T.meters_time_axis_utc || 'Time (UTC)'))
            : (T.meters_time_axis_rel || 'Time before report creation'),
        yTitle: T.meters_power_axis || 'Power [W]',
        zoomXKey: cfg.zoomXKey,
        zoomYKey: cfg.zoomYKey,
        xTickCallback: function(value) {
            return formatTime(value, false);
        },
        tooltipTitleCallback: function(items) {
            if (!items.length) return '';
            const idx = items[0].dataIndex;
            return formatTime(idx, withDecimals)
                + (absolute && !tzKnown ? ' UTC' : '')
                + ' (' + (T.meters_sample_axis || 'Sample') + ' ' + (firstIdx + idx) + ')';
        },
    });
}

function metersHistoryResetZoom() {
    chartResetZoom(metersHistoryChart, 'mhzx', 'mhzy');
}

function metersLiveResetZoom() {
    chartResetZoom(metersLiveChart, 'mlzx', 'mlzy');
}
