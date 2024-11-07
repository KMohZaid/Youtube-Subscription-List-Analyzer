# YouTube Subscription Manager

A comprehensive tool for managing your YouTube subscriptions with enhanced analytics from Social Blade. This tool helps you analyze your subscriptions, track channel growth, and make informed decisions about which channels to keep or unsubscribe from.

## Features

- Fetch all your YouTube channel subscriptions using YouTube Data API
- Enhance subscription data with detailed analytics from Social Blade including:
  - Subscriber count and growth
  - View counts and trends
  - Estimated earnings
  - Upload frequency
  - Channel type and country
  - Historical statistics
- Interactive web interface for viewing and filtering subscriptions
- Sort channels by various metrics (subscribers, views, last upload date)
- Filter channels by upload date range and channel type
- Progress saving and resumption capability for data fetching

## Screenshots

- Checkout [Screenshots](./screenshots/) folder for screenshots
> Yea I know, I'm lazy. Also search/filter input name are confusing. i have todo for it

## Installation

1. Clone this repository:
```bash
git clone [repository-url] # yup placeholder, just check repo url.  This is AI made README.md
cd youtube-subscription-manager
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Set up YouTube API credentials:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable YouTube Data API v3
   - Create OAuth 2.0 credentials
   - Download the credentials file as `credentials.json` and place it in the project root

## Usage

> NOTE: arguments are optional, by default this will use preconfigured argument option

### 1. Fetch Subscriptions

```bash
python main.py fetch --credentials-file credentials.json --output-dir data
```

This will:
- Authenticate with YouTube
- Fetch all your subscriptions
- Save them to `data/subscriptions.csv`

### 2. Enhance Data with Social Blade Statistics

```bash
python main.py enhance --input-file data/subscriptions.csv --output-dir data
```

This will:
- Fetch detailed statistics from Social Blade for each channel
- Save enhanced data to `data/enhanced_subscriptions.csv`
- Support resuming if the process is interrupted

### 3. View Data in Web Interface

```bash
python main.py display --input-file data/enhanced_subscriptions.csv --host 127.0.0.1 --port 5000
```

This will:
- Start a local web server
- Display your subscriptions in an interactive interface
- Allow sorting and filtering of channels

## Current Filtering Options

- Filter by last upload date range
- Filter by channel type
- Sort by subscribers, views, or upload date
- Sort in ascending or descending order

## TODO

### 1. Code Structure Improvements
- [ ] Refactor into a more modular format
- [ ] Separate concerns into different modules
- [ ] Implement proper configuration management
- [ ] Add proper error handling and recovery

### 2. UI Enhancements
- [ ] Proper naming, eg. "Before Last Upload" & "After Last Upload" are confusing. better use "Last Upload Ago" & "Last Upload Not Older Than"
- [ ] Improve overall visual design
- [ ] Add responsive design for mobile devices
- [ ] Implement dark mode
- [ ] Add loading indicators and better error messages

### 3. Channel Information Display
- [ ] Add channel descriptions
- [ ] Display 2-3 latest video thumbnails and titles
- [ ] Show channel engagement metrics
- [ ] Add quick preview functionality

### 4. Bulk Unsubscribe Feature
- [ ] Add checkbox selection for channels
- [ ] Implement bulk ID copying
- [ ] Add unsubscribe confirmation dialog
- [ ] Implement bulk unsubscribe functionality via YouTube API

### 5. Channel Exclusion System
- [ ] Add exclude/hide functionality for channels
- [ ] Create persistent storage for excluded channels
- [ ] Add option to review and restore excluded channels
- [ ] Implement exclusion filters in the main view

## Important Note About Social Blade Data

> Note: Here, we refers to me right now,

This tool uses Social Blade's website to fetch channel statistics. While this provides valuable data for personal use, please be aware that:

1. We acknowledge that this method of data collection may put load on Social Blade's servers
2. This tool is intended for personal use only
3. We apologize to Social Blade for any inconvenience this may cause
4. Consider supporting Social Blade's services if you find their data valuable

For a more proper integration, consider:
- Using Social Blade's official API if available
- Implementing proper rate limiting
- Caching data to reduce server load

## Credits

- YouTube Data API for subscription data
- Social Blade for providing channel statistics
- All the open-source libraries used in this project (see requirements.txt)

## License

- MIT License, ofcourses.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
