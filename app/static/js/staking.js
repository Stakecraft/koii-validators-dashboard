// Initialize UI elements at global scope
let connectButton, disconnectButton, walletStatus, walletStatusText, walletInfo,
    walletAddress, walletBalance, validatorSelect, stakeAmount, availableBalance,
    validatorDetails, validatorCommission, validatorStake, validatorApr,
    stakeButton, unstakeButton, transactionStatus, transactionMessage, errorModal;

// Helper functions
function updateWalletUI(connected, address = null, balance = null) {
    if (!walletStatus) return; // Guard against undefined elements
    walletStatus.classList.toggle('connected', connected);
    walletStatus.classList.toggle('disconnected', !connected);
    walletStatusText.textContent = connected ? 'Connected' : 'Not Connected';
    walletInfo.classList.toggle('hidden', !connected);
    
    if (connected) {
        walletAddress.textContent = address;
        walletBalance.textContent = formatNumber(balance);
        availableBalance.textContent = formatNumber(balance);
        updateStakeButtons();
    } else {
        stakeButton.disabled = true;
        unstakeButton.disabled = true;
    }
}

function updateStakeButtons() {
    if (!stakeButton || !unstakeButton) return; // Guard against undefined elements
    const hasValidator = validatorSelect.value !== '';
    const hasAmount = parseFloat(stakeAmount.value) > 0;
    const hasBalance = parseFloat(availableBalance.textContent.replace(/,/g, '')) > 0;
    stakeButton.disabled = !hasValidator || !hasAmount || !hasBalance;
    unstakeButton.disabled = !hasValidator;
}

function showTransactionStatus(message) {
    if (!transactionStatus) return; // Guard against undefined elements
    transactionStatus.classList.remove('hidden');
    transactionMessage.textContent = message;
}

function showError(message) {
    const errorElement = document.getElementById('error-message');
    if (!errorElement || !errorModal) return; // Guard against undefined elements
    errorElement.textContent = message;
    errorModal.show();
}

function formatNumber(num) {
    return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(num);
}

function calculateValidatorApr(commission) {
    const networkAprElement = document.getElementById('networkApr');
    const networkApr = networkAprElement ? parseFloat(networkAprElement.textContent) : 23.03;
    return (networkApr * (1 - commission / 100)).toFixed(2);
}

async function updateWalletBalance() {
    const result = await window.koiiWallet.getBalance();
    if (result.success) {
        walletBalance.textContent = formatNumber(result.balance);
        availableBalance.textContent = formatNumber(result.balance);
        updateStakeButtons();
    }
}

// Initialize UI and attach event listeners
function initializeUI() {
    // Initialize UI elements
    connectButton = document.getElementById('connect-wallet');
    disconnectButton = document.getElementById('disconnect-wallet');
    walletStatus = document.getElementById('wallet-status');
    walletStatusText = document.getElementById('wallet-status-text');
    walletInfo = document.getElementById('wallet-info');
    walletAddress = document.getElementById('wallet-address');
    walletBalance = document.getElementById('wallet-balance');
    validatorSelect = document.getElementById('validator-select');
    stakeAmount = document.getElementById('stake-amount');
    availableBalance = document.getElementById('available-balance');
    validatorDetails = document.getElementById('validator-details');
    validatorCommission = document.getElementById('validator-commission');
    validatorStake = document.getElementById('validator-stake');
    validatorApr = document.getElementById('validator-apr');
    stakeButton = document.getElementById('stake-button');
    unstakeButton = document.getElementById('unstake-button');
    transactionStatus = document.getElementById('transaction-status');
    transactionMessage = document.getElementById('transaction-message');
    errorModal = new bootstrap.Modal(document.getElementById('errorModal'));

    // Attach event listeners
    if (connectButton) {
        connectButton.addEventListener('click', async () => {
            try {
                if (!window.koiiWallet) {
                    throw new Error('Wallet interface not initialized. Please refresh the page and try again.');
                }

                showTransactionStatus('Connecting to wallet...');
                const result = await window.koiiWallet.connect();
                if (result.success) {
                    updateWalletUI(true, result.publicKey, result.balance);
                    transactionStatus.classList.add('hidden');
                } else {
                    throw new Error(result.error || 'Failed to connect to wallet');
                }
            } catch (error) {
                showError(error.message);
                transactionStatus.classList.add('hidden');
            }
        });
    }

    // ... rest of event listeners and functions ...

    // Initialize UI state
    updateWalletUI(false);
}

// Initialize when the DOM is ready
document.addEventListener('DOMContentLoaded', initializeUI);

// Also initialize when the wallet is ready (in case DOMContentLoaded already fired)
window.addEventListener('walletReady', () => {
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        initializeUI();
    }
});