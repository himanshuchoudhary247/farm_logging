# Chrome DevTools MCP Setup Guide

## Step 1: Install Chrome DevTools MCP Server

Open your terminal and run:

```bash
npm install -g chrome-devtools-mcp
```

If you get permission errors, try:
```bash
npm install -g chrome-devtools-mcp --unsafe-perm
```

Or use npx without global install:
```bash
npx chrome-devtools-mcp --version
```

## Step 2: Update OpenCode Configuration

Edit your OpenCode config file:

```bash
nano ~/.config/opencode/opencode.json
```

Replace the contents with:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": [],
  "provider": {
    "amazon-bedrock": {
      "options": {
        "profile": "alpha",
        "region": "us-east-1"
      }
    }
  },
  "agent": {
    "explore": {
      "disable": true
    },
    "general": {
      "disable": true
    }
  },
  "small_model": "amazon-bedrock/amazon.nova-micro-v1:0",
  "mcpServers": {
    "chrome-devtools": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--isolated"]
    }
  }
}
```

Save the file (Ctrl+X, then Y, then Enter).

## Step 3: Verify Chrome Remote Debugging

Make sure Chrome is installed and can be launched with remote debugging:

On macOS:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --headless &
```

On Linux:
```bash
google-chrome --remote-debugging-port=9222 --headless &
```

On Windows:
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

## Step 4: Test MCP Connection

Once configured, I should be able to use these tools:

- `tabs_context_mcp` - List open tabs
- `navigate` - Load URLs
- `computer` - Click, type, screenshot
- `find` - Locate elements
- `javascript_exec` - Run JS in browser
- `read_network_requests` - Monitor API calls

## Step 5: Test the Login Flow

With MCP enabled, I can:
1. Navigate to http://localhost:5176
2. Take a screenshot
3. Find and click the phone input
4. Type "7987976683"
5. Click Continue
6. Enter OTP "1234"
7. Monitor network requests
8. Check console logs
9. Verify redirect behavior

## Troubleshooting

If Chrome doesn't start with remote debugging:
- Close all Chrome windows first
- Use a different port if 9222 is in use
- Check Chrome is installed at the expected path

If MCP doesn't connect:
- Restart OpenCode after editing config
- Check that npx can find chrome-devtools-mcp
- Verify no firewall is blocking localhost:9222
