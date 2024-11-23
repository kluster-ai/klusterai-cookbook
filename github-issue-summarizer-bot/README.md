# Summarize your GitHub Issues with kluster.ai

This guide will help you set up a Slack bot that leverages kluster.ai's Batch API to efficiently process multiple GitHub issues in batch. Using the state-of-the-art Meta Llama 3.1 405B model, it periodically collects new issues since the last run and processes them as a single batch job, offering several key advantages:

- **Efficient Processing**: Rather than making individual API calls for each issue, the batch API allows simultaneous processing of multiple issues in one request
- **Cost Effective**: Batch processing offers better prices and scalability compared to individual API calls
- **Rate Limit Friendly**: Real-time APIs often have strict limits on requests/tokens per minute/hour - batch processing helps stay within these constraints
- **Automated Workflow**: Set it and forget it - the bot automatically collects issues since its last run and processes them in batches

The bot posts these summaries to a designated Slack channel, helping your team stay up to date on busy repos.

## Setup Instructions

### 1. Repository Setup
1. Clone this repository and cd into it.

2. Create a virtual environment and install packages:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Configuration
You have two options for environment configuration:

1. Create a `.env` file alongside your `config.yaml` (default behavior)
2. Specify a custom `.env` file location using the `--env` flag when running the script

Your `.env` file should contain:
```bash
KLUSTERAI_API_KEY=your_klusterai_api_key
GH_TOKEN=your_github_personal_access_token
SLACK_TOKEN=your_slack_bot_token
```

### 3. Getting Required Tokens

#### kluster.ai API Key
1. Sign up at [kluster.ai](https://kluster.ai)
3. Go to [API Keys section](https://platform.kluster.ai/api-keys)
4. Generate a new API key
5. Copy the API key and store it securely

#### GitHub Token
1. Go to [GitHub Settings > Developer settings > Personal access tokens > Tokens (classic)](https://github.com/settings/tokens)
2. Click "Generate new token (classic)"
3. Give your token a descriptive name
4. The next step isn't required for public repos. If your bot will access private repos, select the following scopes:
   - `repo` (Full control of private repositories)
   - `read:org` (Read org and team membership)
5. Click "Generate token"
6. Copy the token immediately (you won't be able to see it again)

#### Slack Token
1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App"
3. Choose "From an app manifest"
4. Select your workspace and click "Next"
5. Paste the following manifest:
```json
{
    "display_information": {
        "name": "kluster.ai GitHub issues summarizer",
        "description": "I produce daily summaries produced by the kluster.ai batch API of GithHub issues.",
        "background_color": "#4a154b"
    },
    "features": {
        "bot_user": {
            "display_name": "kluster.ai GH issue summarizer",
            "always_online": true
        }
    },
    "oauth_config": {
        "scopes": {
            "bot": [
                "chat:write"
            ]
        }
    },
    "settings": {
        "org_deploy_enabled": false,
        "socket_mode_enabled": false,
        "token_rotation_enabled": false
    }
}
```
6. Click "Create"
7. Click "Install to Workspace"
8. Invite the bot to your target channel using `/invite ` and selecting the app.
8. After installation, navigate to "OAuth & Permissions" in the sidebar
10. Copy the "Bot User OAuth Token" (starts with `xoxb-`)

Store all these tokens in your `.env` file as shown in the Environment Configuration section.



### 4. Configuration Settings
Update the `config.yaml` file with your settings:

```yaml
kluster:
  base_url: "http://api.kluster.ai/v1"
  model: "klusterai/Meta-Llama-3.1-405B-Instruct-Turbo"

github:
  owner: "your-github-org"
  repo: "your-repo-name"

slack:
  channel: "your-slack-channel"

limits:
  input_tokens: 100000
```

### 5. Try!
Before setting up automation, let's test the script manually:

1. Make sure your virtual environment is activated:
```bash
source .venv/bin/activate
```

2. Run the script:
```bash
python3 main.py
```

You should see output similar to this:
```
Fetching GitHub issues since 2024-03-20T10:00:00Z
Found 50 new issues to process
Batch file uploaded. File id: file-abc123
Batch request submitted. Batch ID: batch-xyz789
Batch status: InProgress
Completed requests: 2 / 50
Batch status: InProgress
Completed requests: 25 / 50
Batch status: InProgress
Completed requests: 50 / 50
Batch status: Completed
Posting summaries to Slack...
Done! Check your Slack channel for the summaries.
```

If you encounter any errors:
- Check that all your tokens in `.env` are correct
- Verify your `config.yaml` settings
- Ensure the Slack bot is invited to your channel

Once you've confirmed everything works, proceed to set up automated running via cron.

### 6. Script Setup for Cron
Make the run script executable:
```bash
chmod +x run_github_report.sh
```

### 7. Scheduling
Add a cron job to run the script periodically:
```bash
# Example: Run daily at 9 AM
0 9 * * * /path/to/where/you/cloned/github-summarizer/run_github_report.sh
```

## How It Works
This app is composed of just a few simple steps.

### 1. Fetch Issues
The script checks for new or updated GitHub issues since the last run.

```python
def fetch_github_issues() -> list:
    """
    Fetches GitHub issues created or updated since the last run time.
    
    Returns:
        list: List of GitHub issue objects containing title, body, comments_url, etc.
    """
    since = get_last_run_time()
    github_url = f"https://api.github.com/repos/{CONFIG['github']['owner']}/{CONFIG['github']['repo']}/issues"
    headers = {"Authorization": f"token {CONFIG['github']['token']}"}
    params = {"since": since.isoformat()}
    
    issues = []
    page = 1
    while True:
        params["page"] = page
        try:
            response = requests.get(github_url, headers=headers, params=params)
            response.raise_for_status()
            page_issues = response.json()
            
            if not page_issues:
                break
            
            issues.extend(page_issues)
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"Error fetching GitHub issues: {e}")
            return []
    
    return issues
```

### 2. Prepare Batch Job
Each issue is prepared for summarization, including its title, body, and comments.

```python
def prepare_klusterai_job(issues: list, tokenizer) -> list:
    """
    Prepares a list of requests for kluster.ai batch processing.
    
    Args:
        issues: List of GitHub issues
        tokenizer: Tokenizer instance for text processing
        
    Returns:
        List of task dictionaries ready for batch processing
    """
    tasks = []
    for i, issue in enumerate(issues):
        title = issue.get("title", "")
        body = issue.get("body", "")
        issue_url = issue.get("html_url", "")
        
        comments_text = ""
        if issue.get("comments", 0) > 0:
            comments_text = fetch_issue_comments(
                issue.get("comments_url", ""),
                {"Authorization": f"token {CONFIG['github']['token']}"},
                tokenizer
            )

        task = {
            "custom_id": f"issue-{i+1}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": CONFIG['klusterai']['model'],
                "messages": [
                    {"role": "system", "content": (
                        "You are a helpful assistant that summarizes GitHub issues. "
                        "Summarize the user provided information about a GitHub issue. "
                        "Provide a Tl;DR summary first, then a detailed summary. "
                        "Use formatting suitable for Slack. "
                        "This means a single * for making titles bold. NEVER use ** for bolding text. "
                        "When formatting code blocks, use triple backticks without specifying the language name."
                    )},
                    {"role": "user", "content": f"Title: {title}. Body: {body}. Comments: {comments_text}"},
                ],
            },
            "metadata": {
                "issue_url": issue_url,
                "title": title
            }
        }
        tasks.append(task)
    return tasks
```

### 3. Submit Batch Job
The requests that have just been prepared are are sent to kluster.ai's Batch API for summarization.

```python
def submit_klusterai_job(tasks: list, file_name: str = "batch_input.jsonl"):
    """
    Submits a batch processing job to kluster.ai and monitors its completion.
    
    Args:
        tasks: List of task dictionaries to process
        file_name: Name of the temporary JSONL file to store tasks
        
    Returns:
        BatchStatus: Object containing the final status of the batch job
    """
    with open(file_name, "w") as file:
        for task in tasks:
            file.write(json.dumps(task) + "\n")

    client = OpenAI(
        api_key=CONFIG['klusterai']['api_key'],
        base_url=CONFIG['klusterai']['base_url']
    )

    batch_input_file = client.files.create(
        file=open(file_name, "rb"),
        purpose="batch"
    )
    print(f"Batch file uploaded. File id: {batch_input_file.id}")

    response = client.batches.create(
        input_file_id=batch_input_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    print(f"Batch request submitted. Batch ID: {response.id}")

    # so we know when the last issues in this batch were processed
    update_last_run_time() 

    while True:
        batch_status = client.batches.retrieve(response.id)
        print("Batch status: {}".format(batch_status.status))
        print(
            f"Completed requests: {batch_status.request_counts.completed} / {batch_status.request_counts.total}"
        )

        if batch_status.status.lower() in ["completed", "failed", "canceled"]:
            break

        time.sleep(10)
        
    save_results(batch_status, client)
    return batch_status
```

### 4. Post to Slack Batch Job results
Summaries are formatted and posted to your Slack channel.

```python
def post_to_slack(channel: str, text: str, token: str):
    """
    Posts a message to a Slack channel.
    
    Args:
        channel: Name of the Slack channel
        text: Message text to post
        token: Slack API token
        
    Raises:
        Prints error message if posting fails (e.g., bot not in channel)
    """
    slack_url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    data = {
        "channel": channel,
        "text": text,
        "unfurl_links": False,
        "unfurl_media": False
    }
    response = requests.post(slack_url, headers=headers, json=data)
    response_data = response.json()
    
    if not response_data.get("ok"):
        error = response_data.get("error", "Unknown error")
        print(f"Failed to send message to Slack: {error}")
        if error == "not_in_channel":
            print("The bot is not in the channel. Please invite the bot to the channel.")
```
