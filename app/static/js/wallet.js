// Koii Network Wallet Integration
class FinnieWallet {
    constructor() {
        this.connected = false;
        this.publicKey = null;
        this.balance = null;
        this.network = 'mainnet';
        this.finnieReady = false;
        this.initialized = false;
    }

    async initialize() {
        try {
            // Check if window.k2 is available
            if (typeof window.k2 !== 'undefined') {
                this.finnieReady = true;
                this.initialized = true;
                window.dispatchEvent(new Event('walletReady'));
                return true;
            }

            // If not immediately available, wait for k2
            const isWalletAvailable = await this.waitForWallet();
            this.finnieReady = isWalletAvailable;
            this.initialized = true;
            
            if (isWalletAvailable) {
                window.dispatchEvent(new Event('walletReady'));
            }
            
            return isWalletAvailable;
        } catch (error) {
            console.error('Failed to initialize wallet:', error);
            return false;
        }
    }

    async waitForWallet(timeout = 2000) {
        if (typeof window.k2 !== 'undefined') {
            this.finnieReady = true;
            return true;
        }

        return new Promise((resolve) => {
            let elapsed = 0;
            const interval = 100;
            const checkWallet = setInterval(() => {
                elapsed += interval;
                if (typeof window.k2 !== 'undefined') {
                    clearInterval(checkWallet);
                    this.finnieReady = true;
                    resolve(true);
                } else if (elapsed >= timeout) {
                    clearInterval(checkWallet);
                    this.finnieReady = false;
                    resolve(false);
                }
            }, interval);
        });
    }

    async connect() {
        try {
            // If not initialized, try to initialize
            if (!this.initialized) {
                await this.initialize();
            }

            // Check for k2
            if (typeof window.k2 === 'undefined') {
                // Try one more time with a longer timeout
                const isAvailable = await this.waitForWallet(3000);
                if (!isAvailable) {
                    throw new Error('Finnie wallet not detected. Please make sure the extension is installed and refresh the page.');
                }
            }

            // Request wallet connection using k2
            const result = await window.k2.connect();
            if (!result || !result.publicKey) {
                throw new Error('Failed to connect to Finnie wallet. Please make sure the extension is unlocked and try again.');
            }

            this.publicKey = result.publicKey;
            this.connected = true;
            
            // Get initial balance
            await this.getBalance();
            
            return {
                success: true,
                publicKey: this.publicKey,
                balance: this.balance
            };
        } catch (error) {
            console.error('Failed to connect to Finnie wallet:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    async disconnect() {
        try {
            if (typeof window.k2 !== 'undefined') {
                await window.k2.disconnect();
            }
            this.connected = false;
            this.publicKey = null;
            this.balance = null;
            return { success: true };
        } catch (error) {
            console.error('Failed to disconnect from Finnie wallet:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    async getBalance() {
        try {
            if (!this.connected || !this.publicKey) {
                throw new Error('Wallet not connected');
            }

            const balance = await window.k2.getBalance(this.publicKey);
            this.balance = balance;
            return {
                success: true,
                balance: this.balance
            };
        } catch (error) {
            console.error('Failed to get wallet balance:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    async signTransaction(transaction) {
        try {
            if (!this.connected) {
                throw new Error('Wallet not connected');
            }

            const signedTx = await window.k2.signTransaction(transaction);
            return {
                success: true,
                signedTransaction: signedTx
            };
        } catch (error) {
            console.error('Failed to sign transaction:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    async signAndSendTransaction(transaction) {
        try {
            if (!this.connected) {
                throw new Error('Wallet not connected');
            }

            const signature = await window.k2.signAndSendTransaction(transaction);
            return {
                success: true,
                signature: signature
            };
        } catch (error) {
            console.error('Failed to sign and send transaction:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    async switchNetwork(network) {
        try {
            if (typeof window.k2 === 'undefined') {
                throw new Error('Wallet not initialized');
            }

            await window.k2.switchNetwork(network);
            this.network = network;
            return { success: true };
        } catch (error) {
            console.error('Failed to switch network:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }
}

// Initialize wallet instance
window.koiiWallet = new FinnieWallet();

// Initialize wallet when the page loads
window.addEventListener('load', async () => {
    if (window.koiiWallet && !window.koiiWallet.initialized) {
        await window.koiiWallet.initialize();
    }
}); 