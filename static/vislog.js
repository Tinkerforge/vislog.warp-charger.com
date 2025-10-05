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

function make_jsonview(json, selector) {
    const tree = jsonview.create(json);
    jsonview.render(tree, document.querySelector(selector));
    // To only show modified configs, don't expand the tree, only toggle the head and then expand the important children below.
    //jsonview.toggleNode(tree);
    jsonview.expand(tree);
    jsonview.traverse(tree, function(node) {
        if(node.key.includes('modified')) {
            if(node.value.modified == 2) {
                search = node.key.replace('_modified', '')
                jsonview.traverse(tree, function(node) {
                    if(node.key == search) {
                        node.el.classList.add("important");
                        //jsonview.expand(node);
                        // color children?
                        //node.children.forEach((child) => {
                        //    child.el.classList.add("important");
                        //});
                    }
                });
            }
        }
    });
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
    make_jsonview(data.report_json, '#report-json')

    document.getElementById('report-log-text').value = data.report_log;
    document.getElementById('report-trace-text').value = data.report_trace;
    document.getElementById('report-dump-text').value = data.report_dump;
}
