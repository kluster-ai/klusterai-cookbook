# Summarize your GitHub Issues with kluster.ai

This guide will help you set up a Slack bot that leverages kluster.ai's Batch API to efficiently process multiple GitHub issues in batch. Using the state-of-the-art Meta Llama 3.1 405B model, it periodically collects new issues since the last run and processes them as a single batch job, offering several key advantages:

- **Efficient Processing**: Rather than making individual API calls for each issue, the batch API allows simultaneous processing of multiple issues in one request
- **Cost Effective**: Batch processing offers better prices and scalability compared to individual API calls
- **Rate Limit Friendly**: Real-time APIs often have strict limits on requests/tokens per minute/hour - batch processing helps stay within these constraints
- **Automated Workflow**: Set it and forget it - the bot automatically collects issues since its last run and processes them in batches

The bot posts these summaries to a designated Slack channel, helping your team stay up to date on busy repos.

Before diving into the setup, let's understand the batch processing workflow, or if you already know, you can [skip straight to the setup instructions](#setup-instructions)!

## How Batch Processing Works

New to using Batch APIs? Think of it like sending a big batch of laundry to be cleaned, rather than washing one item at a time. Here's how it works:

1. **Create and Upload Your Request File**
First, you create a JSONL file (think: JSON, but one complete request per line). Here's what it looks like:

```json
{
    "custom_id": "issue-1",
    "method": "POST",
    "url": "/v1/chat/completions",
    "body": {
        "model": "klusterai/Meta-Llama-3.1-405B-Instruct-Turbo",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant that summarizes GitHub issues."
            },
            {
                "role": "user",
                "content": "Repository: klusterai-cookbook. Title: Issue rendering notebooks on small screens. Body:Tested on a bunch of phones and tablets.1. Comments: Happens for me too on...."
            }
        ]
    }
}
```

The actual JSONL file will contain multiple requests, one per line. For example:
```json
{"custom_id": "issue-1", "method": "POST", ...}
{"custom_id": "issue-2", "method": "POST", ...}
{"custom_id": "issue-3", "method": "POST", ...}
```

Then upload and submit it:
```python
def submit_klusterai_job(client: OpenAI, last_run_file: Path, file_dir: Path) -> str:
    # Upload your JSONL file of requests
    batch_input_file = client.files.create(
        file=open(input_path, "rb"),
        purpose="batch"    # Tell kluster.ai this is for batch processing
    )
    
    # Start the batch job - it will process all requests in your file
    response = client.batches.create(
        input_file_id=batch_input_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",    # Job will complete within 24 hours
    )
    return response.id
```

2. **Watch Your Job's Progress**
Like tracking a delivery, you can monitor how many requests have been processed:
```python
def monitor_batch_status(client, batch_id: str, interval: int = 10) -> dict:
    while True:
        batch_status = client.batches.retrieve(batch_id)
        # Shows progress like: "Completed requests: 45 / 100"
        print(f"Completed requests: {batch_status.request_counts.completed} / {batch_status.request_counts.total}")

        # Check if job is done (or had problems)
        if batch_status.status.lower() in ["completed", "failed", "canceled"]:
            break
        time.sleep(interval)    # Wait 10 seconds before checking again
    return batch_status
```

3. **Get Your Results**
When complete, you'll get back a JSONL file with all your results:
```python
def retrieve_result_file_contents(batch_status, client, file_dir: Path) -> Path:
    # Download your results file
    result_file_id = batch_status.output_file_id
    results = client.files.content(result_file_id).content
    
    # Save to your computer
    result_path = file_dir / "batch_results.jsonl"
    with open(result_path, "wb") as file:
        file.write(results)
```

The results file will look something like this:
```json
{"id": "1a3157a8", "custom_id": "issue-1", "response": {"status_code": 200, "body": {"choices": [{"message": {"content": "*TL;DR Summary*: Crashing becoming more common..."}}]}}}
{"id": "2b4268b9", "custom_id": "issue-2", "response": {"status_code": 200, "body": {"choices": [{"message": {"content": "*TL;DR Summary*: Users having issues logging in recently..."}}]}}}
....
```

## Setup Instructions

### 1. Quick Start with Docker Compose

The easiest way to run this bot is using Docker Compose:

1. Clone this repository and cd into it.

2. Create a `.env` file with your API keys (see [Getting Required Tokens](#getting-required-tokens) below):
```bash
KLUSTERAI_API_KEY=your_klusterai_api_key
GH_TOKEN=your_github_personal_access_token
SLACK_TOKEN=your_slack_bot_token
```

3. Configure your settings in `docker-compose.yml`:
```yaml
services:
  klusterai-github-summary-bot:
    build: .
    env_file:
      - .env
    environment:
      - CRON_SCHEDULE=0 9 * * *  # Run daily at 9 AM
      - RUN_NOW=true            # Run immediately when container starts
      - GITHUB_ORG=your-org     # Your GitHub organization
      - GITHUB_REPO=your-repo   # Optional: specific repo (remove for org-wide)
      - SLACK_CHANNEL=your-channel
      # Optional: adjust these as needed
      - BATCH_CLEANUP=true
      - KEEP_DAYS=7 # days to keep local files
      - DEBUG=true 
```

4. Start the bot:
```bash
docker compose up -d
```

The bot will run according to the schedule you set in `CRON_SCHEDULE`. You can view logs with:
```bash
docker compose logs -f
```

### Getting Required Tokens

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
        "description": "I produce regular summaries of GitHub issues using the kluster.ai batch API.",
        "background_color": "#4a154b"
    },
    "features": {
        "bot_user": {
            "display_name": "GitHub Issue Summaries by kluster.ai",
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

### Configuration Options

When running with Docker Compose, you can configure the bot using environment variables in your `docker-compose.yml`:

| Variable | Description | Default |
|----------|-------------|---------|
| CRON_SCHEDULE | When to run the bot (cron syntax) | `0 9 * * *` (9 AM daily) |
| RUN_NOW | Run immediately on startup | `true` |
| GITHUB_ORG | A GitHub organization to monitor| Required |
| GITHUB_REPO | Specific repository to monitor | Optional |
| SLACK_CHANNEL | Slack channel for summaries | Required |
| MAX_INPUT_TOKENS_PER_REQUEST | maximum input token limit per request | 100000 |
| BATCH_CLEANUP | Clean up old local batch files | `true` |
| KEEP_DAYS | Days to keep blocal atch files | 7 |
| DEBUG | Print to console instead of Slack | `false` |

## How It Works
This app processes GitHub issues in a few key steps:

### 1. Fetch Issues
The script checks for new or updated GitHub issues since the last run. It can either monitor a single repository or all repositories in an organization.

```python
def fetch_github_issues(
    github_token: str,
    owner: str,
    repo: str | None,
    last_run_file: Path
) -> list:
    since = get_last_run_time(last_run_file)
    headers = {"Authorization": f"token {github_token}"}
    
    all_issues = []
    repos_to_check = [repo] if repo else fetch_org_repos(owner, headers)
    
    for repo in repos_to_check:
        github_url = f"https://api.github.com/repos/{owner}/{repo}/issues"
        # Fetches issues and their comments, respecting token limits
        # Returns list of issues with their content
```

### 2. Process GitHub Post and Comments
Each issue's content (title, body, and comments) is processed to fit within token limits. Comments are included if space allows after the main content.

```python
def process_issue_content(issue: dict, input_token_limit: int, headers: dict) -> dict:
    base_content = f"Repository: {issue['repository_name']}\nTitle: {issue['title']}\nBody: {issue['body']}"
    base_tokens = calculate_tokens(base_content)
    
    if base_tokens > input_token_limit:
        # Truncate if needed
        print(f"Issue {issue['number']} exceeds token limit. Truncating body.")
    else:
        # Fetch comments if space allows
        remaining_tokens = input_token_limit - base_tokens
        if issue.get("comments", 0) > 0 and remaining_tokens > 0:
            issue['comments_text'] = fetch_issue_comments(...)
```

### 3. Prepare and Submit Batch Job
The processed issues are formatted into a batch job for kluster.ai's API. Each issue becomes a task in the batch, with proper prompting for summarization.

```python
def prepare_klusterai_job(
    model: str,
    requests: list,
    batch_dir: str = "batch_files"
) -> Tuple[list, Path]:
    tasks = []
    for request in requests:
        task = {
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant..."},
                    {"role": "user", "content": f"Repository: {repo_name}\nTitle: {title}\nBody: {body}\nComments: {comments_text}"},
                ],
            },
            "metadata": {
                "issue_url": issue_url,
                "title": title,
                "repo_name": repo_name
            }
        }
        tasks.append(task)
```


### 4. Monitor and Process Results
Once the batch job completes, the script processes the results, organizing them by repository.

```python
def process_and_post_results(
    org_name: str,
    slack_channel: str,
    slack_token: str,
    file_dir: Path,
    debug: bool = False
) -> None:
    # Organize results by repository
    repo_results = {}
    for result in results:
        repo_name = result.get("repo_name", "unknown")
        if repo_name not in repo_results:
            repo_results[repo_name] = []
        
        repo_results[repo_name].append(
            f"*Title:* <{issue_url}|[{title}]>\n{summary}\n"
        )
```

### 5. Post to Slack
Finally, the organized summaries are posted to Slack, grouped by repository for better readability.

```python
def post_to_slack(channel: str, text: str, token: str):
    slack_url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # Split message into chunks if needed
    chunks = chunk_message(text)
    
    for chunk in chunks:
        data = {
            "channel": channel,
            "text": chunk,
            "unfurl_links": False,
            "unfurl_media": False
        }
```

The script also includes automatic cleanup of old batch files, controlled by these settings:
```yaml
processing:
  batch:
    cleanup: true  # Enable/disable cleanup
    keep_days: 7   # Number of days to keep files
    generated_files_directory: batch_files  # Directory to clean
```

## Organization-wide Summaries

This tool can monitor issues across all repositories in your GitHub organization. To enable this:

1. Remove the repo field in `config.yaml`:
```yaml
api:
  github:
    owner: "your-github-org"
    # repo field removed for org-wide monitoring
```

2. Ensure your GitHub token has appropriate permissions:
   - For public repositories: `public_repo` scope is sufficient
   - For private repositories: `repo` scope is required
   - The `read:org` scope is required to list organization repositories

When running in organization-wide mode, the tool will:
1. First fetch all accessible repositories in your organization
2. Then check for new issues in each repository since the last run
3. Group the summaries by repository when posting to Slack

This is particularly useful for:
- Organizations with many active repositories
- Teams that need to monitor issue activity across multiple projects
- Managers tracking engagement across an organization

