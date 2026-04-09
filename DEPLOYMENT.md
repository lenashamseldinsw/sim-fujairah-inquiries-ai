# Deployment Guide - Fujairah Pulse

## Deploying to Streamlit Cloud

### Prerequisites
- GitHub account
- Streamlit Cloud account (free at [share.streamlit.io](https://share.streamlit.io))

### Step 1: Push to GitHub
This repository should already be pushed to GitHub. If not:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

### Step 2: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click "New app"
4. Select your repository: `sim-fujairah-inquiries-ai`
5. Set the main file path: `app.py`
6. Click "Advanced settings"

### Step 3: Configure Secrets

In the Streamlit Cloud deployment settings, add the following secrets in TOML format:

```toml
[users]
admin_username = "admin"
admin_password = "admin123"
demo_username = "demo"
demo_password = "demo123"
```

**Important:** Change these default passwords to secure ones before deploying to production!

### Step 4: Deploy

Click "Deploy!" and wait for your app to build and launch.

## Local Development

### Setup
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

### Local Secrets
For local development, the app will use `credentials.json` if available. Alternatively, create `.streamlit/secrets.toml`:

```toml
[users]
admin_username = "admin"
admin_password = "admin123"
demo_username = "demo"
demo_password = "demo123"
```

## Security Notes

1. **Never commit secrets to git** - The `.gitignore` file is configured to exclude:
   - `.streamlit/secrets.toml`
   - `credentials.json`
   - `.env` files

2. **Change default passwords** - Update the default credentials before production deployment

3. **Use environment variables** - For production, consider using more secure authentication methods

## File Structure

```
sim-fujairah-inquiries-ai/
├── app.py                 # Main application
├── report_display.py      # Report display module
├── requirements.txt       # Python dependencies
├── .gitignore            # Git ignore rules
├── .streamlit/
│   └── secrets.toml      # Local secrets (not committed)
├── assets/               # Images and static files
├── outputs/              # Generated reports
└── credentials.json      # Local credentials (not committed)
```

## Troubleshooting

### App won't start on Streamlit Cloud
- Check that all dependencies are listed in `requirements.txt`
- Verify secrets are properly configured in Streamlit Cloud settings
- Check the app logs in Streamlit Cloud dashboard

### Authentication not working
- Verify secrets are properly formatted in TOML
- Check that the secrets section name is `[users]`
- Ensure no extra spaces or special characters in credentials

### Missing files or assets
- Ensure all required files are committed to git
- Check that `.gitignore` isn't excluding necessary files
- Verify asset paths are relative, not absolute

## Support

For issues or questions, contact the development team.
