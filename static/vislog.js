let chart  = undefined;
let config = undefined;
let originalDatasets = undefined;

function open_tab(evt, tab) {
    var i, tabcontent, tablinks;

    // Get all elements with class="tabcontent" and hide them
    tabcontent = document.getElementsByClassName("tabcontent");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }

    // Get all elements with class="tablinks" and remove the class "active"
    tablinks = document.getElementsByClassName("tablinks");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }

    // Show the current tab, and add an "active" class to the button that opened the tab
    document.getElementById(tab).style.display = "block";
    evt.currentTarget.className += " active";
}

function log_axis_clicked() {
    checkbox = document.getElementById('log-axis');

    chart.destroy()
    if(checkbox.checked) {
        config.options.scales.y = {
            display: true,
            type: 'logarithmic',
            ticks: {
                color: '#f0f0f0'
            },
            grid: {
                color: '#3a3a3a'
            }
        }
    } else {
        config.options.scales.y = {
            display: true,
            ticks: {
                color: '#f0f0f0'
            },
            grid: {
                color: '#3a3a3a'
            }
        }
    }
    chart = new Chart(document.getElementById('warp_chart'), config);
}

function toggle_column_visibility(column_name, visible) {
    const datasetIndex = config.data.datasets.findIndex(dataset =>
        dataset.csv_column === column_name
    );

    if (datasetIndex !== -1) {
        if (visible) {
            // Show the dataset
            config.data.datasets[datasetIndex].hidden = false;
        } else {
            // Hide the dataset
            config.data.datasets[datasetIndex].hidden = true;
        }
        chart.update('none'); // Update without animation for better performance
    }
}

function toggle_all_columns(visible) {
    const checkboxes = document.querySelectorAll('#column-checkboxes input[type="checkbox"]:not([style*="display: none"])');
    checkboxes.forEach(checkbox => {
        checkbox.checked = visible;
        const columnName = checkbox.dataset.column;
        toggle_column_visibility(columnName, visible);
    });
}

function filter_columns() {
    const searchTerm = document.getElementById('column-search').value.toLowerCase();
    const columnItems = document.querySelectorAll('.column-item');
    let visibleCount = 0;

    columnItems.forEach(item => {
        const label = item.querySelector('label').textContent.toLowerCase();
        if (label.includes(searchTerm)) {
            item.style.display = 'flex';
            visibleCount++;
        } else {
            item.style.display = 'none';
        }
    });

    update_column_count(visibleCount, columnItems.length);
}

function update_column_count(visible, total) {
    const countElement = document.getElementById('column-count');
    if (visible < total) {
        countElement.textContent = `${visible} von ${total} Spalten angezeigt`;
    } else {
        countElement.textContent = `${total} Spalten verfügbar`;
    }
}

function create_column_selector(datasets) {
    const container = document.getElementById('column-checkboxes');
    container.innerHTML = '';

    datasets.forEach((dataset, index) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'column-item';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = 'col-' + index;
        checkbox.dataset.column = dataset.csv_column;
        checkbox.checked = !dataset.hidden;

        checkbox.addEventListener('change', function() {
            toggle_column_visibility(dataset.csv_column, this.checked);
        });

        const label = document.createElement('label');
        label.htmlFor = checkbox.id;
        label.textContent = dataset.label;
        label.title = dataset.label; // Add tooltip for long names

        wrapper.appendChild(checkbox);
        wrapper.appendChild(label);
        container.appendChild(wrapper);
    });

    // Initialize count display
    update_column_count(datasets.length, datasets.length);
}

function make_jsonview(json, selector, options = {}) {
    const container = document.querySelector(selector);
    const tree = jsonview.create(json);

    // Create enhanced JSON viewer container
    const wrapper = document.createElement('div');
    wrapper.className = 'enhanced-json-viewer';

    // Add search and filter controls
    const controls = document.createElement('div');
    controls.className = 'json-controls';
    controls.innerHTML = `
        <div class="json-search-container">
            <input type="text" class="json-search" placeholder="Search configurations... (Enter: next, Shift+Enter: previous)" />
            <div class="search-results-count"></div>
        </div>
        <div class="json-filters-actions">
            <div class="json-filters">
                <button class="filter-btn active" data-filter="all" title="Show all configurations">All</button>
                <button class="filter-btn" data-filter="modified" title="Show only modified configurations">Modified</button>
                <button class="filter-btn" data-filter="numbers" title="Show only numeric values">Numbers</button>
                <button class="filter-btn" data-filter="strings" title="Show only string values">Strings</button>
                <button class="filter-btn" data-filter="booleans" title="Show only boolean values">Booleans</button>
                <button class="filter-btn" data-filter="objects" title="Show only object/array values">Objects</button>
            </div>
            <div class="json-actions">
                <button class="action-btn" onclick="expandAllJson('${selector}')" title="Expand all nodes">Expand All</button>
                <button class="action-btn" onclick="collapseAllJson('${selector}')" title="Collapse all nodes">Collapse All</button>
            </div>
        </div>
    `;

    // Create JSON content container
    const jsonContent = document.createElement('div');
    jsonContent.className = 'json-content';

    wrapper.appendChild(controls);
    wrapper.appendChild(jsonContent);
    container.innerHTML = '';
    container.appendChild(wrapper);

    // Render JSON tree
    jsonview.render(tree, jsonContent);
    jsonview.expand(tree);

    // Store tree reference on the container for later use
    container._jsonTree = tree;    // Enhanced highlighting and processing
    jsonview.traverse(tree, function(node) {
        // Add data type classes
        if (node.el && node.value !== null) {
            const valueType = typeof node.value;
            node.el.classList.add(`json-type-${valueType}`);

            // Add timestamp formatting
            if (typeof node.value === 'number' && node.value > 1000000000 && node.value < 9999999999) {
                const date = new Date(node.value * 1000);
                if (!isNaN(date.getTime())) {
                    const timeEl = document.createElement('span');
                    timeEl.className = 'timestamp-hint';
                    timeEl.textContent = ` (${date.toLocaleString()})`;
                    const valueEl = node.el.querySelector('.json-value');
                    if (valueEl) valueEl.appendChild(timeEl);
                }
            }
        }

        // Handle modified configurations
        if(node.key && node.key.includes('modified')) {
            if(node.value && (node.value.modified == 1 || node.value.modified == 2 || node.value.modified == 3)) {
                search = node.key.replace('_modified', '')
                jsonview.traverse(tree, function(searchNode) {
                    if(searchNode.key == search) {
                        if (node.value.modified == 1 || node.value.modified == 3) {
                            searchNode.el.classList.add("important");
                        }
                        searchNode.el.classList.add("modified-config");
                    }
                });
            }
        }
    });

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
                    const keyMatch = node.key && node.key.toLowerCase().includes(searchTerm);
                    const valueMatch = node.value && String(node.value).toLowerCase().includes(searchTerm);

                    if (keyMatch || valueMatch) {
                        node.el.classList.add('search-highlight');
                        searchResults.push(node.el);
                    }
                }
            });

            resultsCount.textContent = `${searchResults.length} matches`;
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

            resultsCount.textContent = `${currentSearchIndex + 1} of ${searchResults.length} matches`;
        }
    });

    // Add filter functionality
    const filterBtns = wrapper.querySelectorAll('.filter-btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            filterBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            const filter = this.dataset.filter;

            if (filter === 'modified') {
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
                jsonview.traverse(tree, function(node) {
                    if (node.el) {
                        let show = true;

                        switch(filter) {
                            case 'numbers':
                                show = node.el.classList.contains('json-type-number');
                                break;
                            case 'strings':
                                show = node.el.classList.contains('json-type-string');
                                break;
                            case 'booleans':
                                show = node.el.classList.contains('json-type-boolean');
                                break;
                            case 'objects':
                                show = node.el.classList.contains('json-type-object');
                                break;
                            case 'all':
                            default:
                                show = true;
                        }

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
            if (node.el && node.el.style.display !== 'none' && node.children.length > 0) {
                jsonview.toggleNode(node); // This will expand if collapsed
                // Make sure it's expanded, not collapsed
                if (!node.isExpanded) {
                    jsonview.toggleNode(node);
                }
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

function vislog_protocol(data) {
    // Store original datasets for reference
    originalDatasets = JSON.parse(JSON.stringify(data.chart.datasets));

    // Add csv_column property to datasets if not present
    data.chart.datasets.forEach((dataset, index) => {
        if (!dataset.csv_column) {
            dataset.csv_column = dataset.label;
        }
    });

    config = {
        type: 'line',
        data: data.chart,
        options: {
            animation: false,
            maintainAspectRatio: false,
            elements: {
                point: {
                    radius: 0
                }
            },
            hover: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                title: {
                    display: true,
                    text: 'Ladeprotokoll',
                    color: '#f0f0f0'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                },
                legend: {
                    labels: {
                        color: '#f0f0f0'
                    }
                },
                zoom: {
                    zoom: {
                        drag: {
                            enabled: true,
                            backgroundColor: 'rgba(85, 85, 85, 0.3)',
                            borderColor: 'rgba(85, 85, 85, 0.8)',
                            borderWidth: 1,
                            threshold: 20,
                        },
                        wheel: {
                            enabled: false,
                        },
                        mode: 'xy',
                    },
                    pan: {
                        enabled: true,
                        mode: 'xy',
                        modifierKey: 'ctrl',
                        threshold: 5,
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    ticks: {
                        color: '#f0f0f0'
                    },
                    grid: {
                        color: '#3a3a3a'
                    }
                },
                y: {
                    display: true,
                    type: 'logarithmic',
                    ticks: {
                        color: '#f0f0f0'
                    },
                    grid: {
                        color: '#3a3a3a'
                    }
                }
            }
        }
    };
    chart = new Chart(document.getElementById('warp_chart'), config);

    // Only create column selector if the element exists (for backward compatibility)
    if (document.getElementById('column-checkboxes')) {
        create_column_selector(data.chart.datasets);
    }

    make_jsonview(data.before_protocol_json, '#before-protocol-json')
    make_jsonview(data.after_protocol_json,  '#after-protocol-json')

    document.getElementById('before-protocol-log-text').value = data.before_protocol_log;
    document.getElementById('after-protocol-log-text').value = data.after_protocol_log;
}

function reset_zoom() {
    if (chart) {
        chart.resetZoom();
    }
}function vislog_report(data) {
    make_jsonview(data.report_json, '#report-json');

    document.getElementById('report-log-text').value = data.report_log;
    document.getElementById('report-trace-text').value = data.report_trace;
    document.getElementById('report-dump-text').value = data.report_dump;

    // Store tree reference for report JSON
    setTimeout(() => {
        const reportContainer = document.querySelector('#report-json');
        if (reportContainer && reportContainer.querySelector('.enhanced-json-viewer')) {
            const tree = reportContainer._jsonTree;
            if (tree) {
                reportContainer._jsonTree = tree;
            }
        }
    }, 100);
}
