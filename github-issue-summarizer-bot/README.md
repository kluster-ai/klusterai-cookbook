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
# API Configuration
api:
  klusterai:
    base_url: "http://api.kluster.ai/v1"
    model: "klusterai/Meta-Llama-3.1-405B-Instruct-Turbo"
  github:
    owner: "your-github-org"
    # repo field removed for org-wide monitoring
  slack:
    channel: "your-slack-channel"

# Processing Settings
processing:
  limits:
    input_tokens_per_request: 100000
  batch:
    cleanup: true
    keep_days: 7
    generated_files_directory: batch_files

# Runtime Settings
runtime:
  debug: true
```

The configuration is organized into three main sections:

1. **API Configuration** (`api`):
   - `klusterai`: Settings for the kluster.ai API
   - `github`: GitHub organization and repository settings
   - `slack`: Slack channel configuration

2. **Processing Settings** (`processing`):
   - `limits`: Controls token limits for requests
   - `batch`: Settings for batch file management
     - `cleanup`: Enable/disable cleanup of old batch files
     - `keep_days`: Number of days to keep batch files
     - `generated_files_directory`: Directory for storing batch files

3. **Runtime Settings** (`runtime`):
   - `debug`: When true, prints messages to console instead of posting to Slack

Note: For organization-wide monitoring, simply remove the `repo` field under `github`:
```yaml
api:
  github:
    owner: "your-github-org"
    # repo field removed for org-wide monitoring
```

### 5. Try!
Before setting up automation, let's test the script manually:

1. Make sure your virtual environment is activated:
```bash
source .venv/bin/activate
```

2. Run the script:
```bash
python3 main.py --config config.yaml --env .env
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

