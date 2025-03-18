# Koii Network Validator Dashboard

A real-time dashboard for monitoring Koii Network validators, built with Flask and modern web technologies.

## Features

- **Real-time Monitoring**: Track validator status, stake, and performance metrics
- **Interactive Map**: Global visualization of validator node locations
- **Responsive Design**: Works seamlessly on desktop and mobile devices
- **Dark/Light Theme**: Automatic theme detection with manual toggle option
- **Performance Optimized**: 
  - Client-side caching
  - Efficient DOM updates
  - Optimized API calls with rate limiting

## Key Metrics Displayed

- Total, Active, and Delinquent Validators
- Network APR
- Average Skip Rate
- Total Active, Current, and Delinquent Stake
- KOII Price (updated every 10 minutes)
- Detailed Validator Information

## Prerequisites

- Option 1: Local Installation
  - Python 3.8+
  - pip (Python package installer)
  - A modern web browser

- Option 2: Docker Installation
  - Docker
  - Docker Compose
  - A modern web browser

## Installation

### Option 1: Local Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd koii-validator-dashboard
```

2. Create and activate a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file:
```bash
cp .env.example .env
```

5. Configure your environment variables in `.env`:
```
# RPC Endpoints
KOII_RPC_URL="https://rpc-koii-mainnet.stakecraft.com:5123"

# Cryptorank API
CRYPTORANK_API_URL="https://api.cryptorank.io/v2/currencies/193384"
CRYPTORANK_API_KEY="your_api_key_here"

# Cache Configuration
PRICE_CACHE_TTL=600  # 10 minutes

# API Endpoints
API_ENDPOINT=/api/nodes

# External URLs
KOII_LOGO_URL=https://img.cryptorank.io/coins/koii1732532262059.png
STAKECRAFT_URL=https://stakecraft.com
STAKECRAFT_TWITTER_URL=https://x.com/stakecraft
STAKECRAFT_TELEGRAM_URL=https://t.me/stakecraft
STAKECRAFT_DISCORD_URL=https://discord.gg/dYPwRZekTd
STAKECRAFT_EMAIL=support@stakecraft.com

# Map Tiles
MAP_LIGHT_TILES_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
MAP_DARK_TILES_URL=https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png

# Update Interval (in milliseconds)
REFRESH_INTERVAL=30000
```

### Option 2: Docker Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd koii-validator-dashboard
```

2. Create and configure the `.env` file:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Build and start the Docker containers:
```bash
docker-compose up -d
```

4. View the logs (optional):
```bash
docker-compose logs -f
```

5. Stop the containers:
```bash
docker-compose down
```

## Running the Application

### Local Installation
1. Start the Flask development server:
```bash
python app/app.py
```

2. Access the dashboard at `http://localhost:5000`

### Docker Installation
1. The application will be automatically started when running `docker-compose up -d`
2. Access the dashboard at `http://localhost:5000`
3. Monitor the application status:
```bash
docker-compose ps    # Check container status
docker-compose logs  # View application logs
```

## Configuration Options

### Cache Settings
- `PRICE_CACHE_TTL`: KOII price cache duration (default: 600 seconds)
- `REFRESH_INTERVAL`: Dashboard update interval (default: 30000 ms)

### API Endpoints
- `KOII_RPC_URL`: Koii Network RPC endpoint
- `CRYPTORANK_API_URL`: Cryptorank API endpoint for KOII price
- `CRYPTORANK_API_KEY`: Your Cryptorank API key

### External Services
- Map tiles for light/dark themes
- Social media links
- Contact information

## Project Structure

```
koii-validator-dashboard/
├── app/
│   ├── static/
│   │   └── css/
│   │       └── style.css
│   ├── templates/
│   │   └── index.html
│   ├── app.py
│   └── config.py
├── .env
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Features in Detail

### Validator Information
- Identity and Vote Account public keys
- Commission rates
- Stake amounts
- Skip rates
- Version information
- Status (Active/Delinquent)

### Map Features
- Clustered markers for better visualization
- Popup information for each validator
- Theme-aware tile layers
- Automatic bounds fitting

### Data Management
- Client-side sorting
- Expandable validator details
- Clipboard copy functionality
- Error handling and display

## Browser Support

The dashboard is compatible with modern web browsers:
- Chrome/Edge (latest 2 versions)
- Firefox (latest 2 versions)
- Safari (latest 2 versions)

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Koii Network for the RPC endpoints
- OpenStreetMap and Stadia Maps for map tiles
- Cryptorank for price data
- Font Awesome for icons 