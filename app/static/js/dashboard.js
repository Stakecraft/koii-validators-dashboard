// Format large numbers with commas
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Format percentage
function formatPercentage(num) {
    return (num * 100).toFixed(2) + '%';
}

// Format stake amount to show in billions/millions
function formatStake(stake) {
    const billion = 1000000000;
    const million = 1000000;
    
    if (stake >= billion) {
        return (stake / billion).toFixed(2) + 'B';
    } else if (stake >= million) {
        return (stake / million).toFixed(2) + 'M';
    }
    return formatNumber(stake);
}

// Sort validators by a specific field
function sortValidators(validators, field, direction) {
    return [...validators].sort((a, b) => {
        let aValue = a[field];
        let bValue = b[field];
        
        // Handle special cases
        if (field === 'delinquent') {
            aValue = aValue ? 1 : 0;
            bValue = bValue ? 1 : 0;
        }
        
        // Handle numeric values
        if (typeof aValue === 'number' && typeof bValue === 'number') {
            return direction === 'asc' ? aValue - bValue : bValue - aValue;
        }
        
        // Handle string values
        if (typeof aValue === 'string' && typeof bValue === 'string') {
            return direction === 'asc' 
                ? aValue.localeCompare(bValue)
                : bValue.localeCompare(aValue);
        }
        
        return 0;
    });
}

// Update the dashboard with new data
function updateDashboard(data) {
    // Update summary cards
    document.getElementById('totalActiveStake').textContent = formatStake(data.totalActiveStake);
    document.getElementById('totalCurrentStake').textContent = formatStake(data.totalCurrentStake);
    document.getElementById('averageSkipRate').textContent = formatPercentage(data.averageSkipRate / 100);
    document.getElementById('weightedSkipRate').textContent = formatPercentage(data.averageStakeWeightedSkipRate / 100);

    // Update version statistics
    const versionStatsContainer = document.getElementById('versionStats');
    versionStatsContainer.innerHTML = '';
    
    for (const [version, stats] of Object.entries(data.stakeByVersion)) {
        const versionDiv = document.createElement('div');
        versionDiv.className = 'version-stat';
        versionDiv.innerHTML = `
            <h6>Version ${version}</h6>
            <div>Current Validators: ${stats.currentValidators}</div>
            <div>Delinquent Validators: ${stats.delinquentValidators}</div>
            <div>Current Active Stake: ${formatStake(stats.currentActiveStake)}</div>
            <div>Delinquent Active Stake: ${formatStake(stats.delinquentActiveStake)}</div>
            <div>Average APR: ${stats.averageApr ? stats.averageApr.toFixed(2) : '-'}%</div>
        `;
        versionStatsContainer.appendChild(versionDiv);
    }

    // Update validators table
    updateValidatorsTable(data.validators);
}

// Update the validators table with sorted data
function updateValidatorsTable(validators) {
    const tableBody = document.querySelector('#validatorsTable tbody');
    tableBody.innerHTML = '';
    
    validators.forEach(validator => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td title="${validator.identityPubkey}">${validator.identityPubkey.slice(0, 8)}...</td>
            <td>${formatStake(validator.activatedStake)}</td>
            <td>${validator.commission}%</td>
            <td>${validator.skipRate !== null ? formatPercentage(validator.skipRate / 100) : 'N/A'}</td>
            <td>${validator.apr !== undefined ? validator.apr.toFixed(2) : '-'}%</td>
            <td>${validator.version || 'Unknown'}</td>
            <td><span class="status-badge ${validator.delinquent ? 'status-delinquent' : 'status-active'}">
                ${validator.delinquent ? 'Delinquent' : 'Active'}
            </span></td>
        `;
        tableBody.appendChild(row);
    });
}

// Initialize sorting state
let currentSort = {
    field: null,
    direction: 'asc'
};

// Handle table header clicks for sorting
document.querySelectorAll('.sortable').forEach(header => {
    header.addEventListener('click', () => {
        const field = header.dataset.sort;
        
        // Remove sort classes from all headers
        document.querySelectorAll('.sortable').forEach(h => {
            h.classList.remove('asc', 'desc');
        });
        
        // Update sort direction
        if (currentSort.field === field) {
            currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
            currentSort.field = field;
            currentSort.direction = 'asc';
        }
        
        // Add sort class to current header
        header.classList.add(currentSort.direction);
        
        // Sort and update table
        const sortedValidators = sortValidators(window.currentValidators, field, currentSort.direction);
        updateValidatorsTable(sortedValidators);
    });
});

// Fetch data from the API
function fetchData() {
    fetch('/api/nodes')
        .then(response => response.json())
        .then(data => {
            // Store validators globally for sorting
            window.currentValidators = data.validators;
            
            // Apply current sort if exists
            if (currentSort.field) {
                const sortedValidators = sortValidators(data.validators, currentSort.field, currentSort.direction);
                updateValidatorsTable(sortedValidators);
            }
            
            updateDashboard(data);
        })
        .catch(error => {
            console.error('Error fetching data:', error);
        });
}

// Initial fetch
fetchData();

// Refresh data every 30 seconds
setInterval(fetchData, 30000); 