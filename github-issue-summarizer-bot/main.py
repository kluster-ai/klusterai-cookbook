import requests
from openai import OpenAI
import json
import time
import os
from datetime import datetime, timedelta
import tiktoken
import yaml
from dotenv import load_dotenv
import argparse
from pathlib import Path

def load_config(config_path: str = 'config.yaml', env_path: str = None):
    """
    Loads configuration from a YAML file and corresponding environment file.
    
    Args:
        config_path: Path to the YAML config file
        env_path: Optional path to specific .env file
        
    Returns:
        dict: Loaded configuration
    """
    # Load environment variables
    if env_path:
        print(f"Loading environment variables from {env_path}")
        load_dotenv(env_path, override=True)
    else:
        # Use same name as config file but with .env extension
        env_file = Path(config_path).with_suffix('.env')
        load_dotenv(env_file, override=True)
    
    print(f"Loading config from {config_path}")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    config['klusterai']['api_key'] = os.getenv("KLUSTERAI_API_KEY")
    config['github']['token'] = os.getenv("GH_TOKEN")
    config['slack']['token'] = os.getenv("SLACK_TOKEN")
    
    # Add a default token limit if not specified in config
    if 'limits' not in config:
        config['limits'] = {}
    if 'input_tokens' not in config['limits']:
        config['limits']['input_tokens'] = 100000
    
    return config

def setup_tokenizer():
    # estimate for simplicity..
    return tiktoken.get_encoding("cl100k_base")

tokenizer = setup_tokenizer()

def calculate_tokens(text, tokenizer):
    """
    Calculates the number of tokens.
    
    Args:
        text: Input text to tokenize
        tokenizer: Tokenizer instance
        
    Returns:
        int: Number of tokens in the text
    """
    return len(tokenizer.encode(text))

def get_last_run_time(last_run_file: Path) -> datetime:
    """
    Retrieves the timestamp of the last successful run.
    
    Args:
        last_run_file: Path to the file storing the last run timestamp
        
    Returns:
        datetime: Timestamp of last run, or 24 hours ago if no record exists
    """
    try:
        with open(last_run_file, 'r') as f:
            timestamp = float(f.read().strip())
            return datetime.fromtimestamp(timestamp)
    except (FileNotFoundError, ValueError):
        # If file doesn't exist or is invalid, default to 24 hours ago
        return datetime.now() - timedelta(days=1)

def update_last_run_time(last_run_file: Path):
    """
    Updates the last run timestamp.
    
    Args:
        last_run_file: Path to store the timestamp
    """
    with open(last_run_file, 'w') as f:
        f.write(str(time.time()))

def fetch_org_repos(owner: str, headers: dict) -> list:
    """
    Fetches all repositories for an organization.
    
    Args:
        owner: GitHub organization name
        headers: Request headers including authentication
        
    Returns:
        list: List of repository names
    """
    github_url = f"https://api.github.com/orgs/{owner}/repos"
    repos = []
    page = 1
    
    while True:
        try:
            response = requests.get(
                github_url, 
                headers=headers,
                params={
                    "page": page, 
                    "per_page": 100,
                    "type": "all"
                }
            )
            response.raise_for_status()
            page_repos = response.json()
            
            if not page_repos:
                break
                
            repos.extend([repo["name"] for repo in page_repos])
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"Error fetching organization repositories: {e}")
            return []
            
    return repos

def fetch_github_issues(
    github_token: str,
    owner: str,
    repo: str | None,
    last_run_file: Path
) -> list:
    """
    Fetches GitHub issues created or updated since the last run time.
    
    Args:
        github_token: GitHub authentication token
        owner: GitHub organization/owner name
        repo: Specific repository name or None to fetch from all repos
        last_run_file: Path to the file storing last run timestamp
    """
    since = get_last_run_time(last_run_file)
    headers = {"Authorization": f"token {github_token}"}
    
    all_issues = []
    repos_to_check = []
    
    if repo:
        repos_to_check = [repo]
    else:
        repos_to_check = fetch_org_repos(owner, headers)
        print(f"Found {len(repos_to_check)} repositories in organization")
    
    for repo in repos_to_check:
        github_url = f"https://api.github.com/repos/{owner}/{repo}/issues"
        params = {"since": since.isoformat()}
        page = 1
        
        while True:
            params["page"] = page
            try:
                response = requests.get(github_url, headers=headers, params=params)
                response.raise_for_status()
                page_issues = response.json()
                
                if not page_issues:
                    break
                
                # Add repo name to each issue for better context
                for issue in page_issues:
                    issue['repository_name'] = repo
                
                all_issues.extend(page_issues)
                page += 1
            except requests.exceptions.RequestException as e:
                print(f"Error fetching GitHub issues for repo {repo}: {e}")
                continue
                
        print(f"Found {len(all_issues)} issues in {repo}")
    
    return all_issues

def fetch_issue_comments(comments_url: str, headers: dict, tokenizer, token_limit: int) -> str:
    """
    Retrieves and concatenates comments for a GitHub issue, respecting token limits.
    
    Args:
        comments_url: URL endpoint for the issue's comments
        headers: Request headers including authentication
        tokenizer: Tokenizer instance for calculating token counts
        token_limit: Maximum number of tokens allowed
        
    Returns:
        str: Concatenated comments text, separated by '---'
    """
    comments_text = ""
    response = requests.get(comments_url, headers=headers)
    comments = response.json()
    
    for comment in comments:
        comment_body = comment.get("body", "")
        current_tokens = calculate_tokens(comments_text, tokenizer)
        new_comment_tokens = calculate_tokens(comment_body, tokenizer)
        
        if current_tokens + new_comment_tokens > token_limit:
            print("Token limit reached for comments.")
            break
        
        if comments_text:
            comments_text += "\n---\n"
        comments_text += comment_body
    
    return comments_text

def prepare_klusterai_job(
    model: str,
    github_token: str,
    input_token_limit: int,
    issues: list,
    tokenizer
) -> list:
    """
    Prepares a list of requests for kluster.ai batch processing.
    
    Args:
        model: The model to use for processing
        github_token: GitHub token for fetching comments
        input_token_limit: Maximum number of tokens allowed
        issues: List of GitHub issues
        tokenizer: Tokenizer instance for text processing
    """
    tasks = []
    for i, issue in enumerate(issues):
        title = issue.get("title", "")
        body = issue.get("body", "")
        issue_url = issue.get("html_url", "")
        repo_name = issue.get("repository_name", "")
        
        comments_text = ""
        if issue.get("comments", 0) > 0:
            comments_text = fetch_issue_comments(
                issue.get("comments_url", ""),
                {"Authorization": f"token {github_token}"},
                tokenizer,
                input_token_limit
            )

        task = {
            "custom_id": f"issue-{i+1}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": (
                        "You are a helpful assistant that summarizes GitHub issues. "
                        "Summarize the user provided information about a GitHub issue. "
                        "Provide a Tl;DR summary first, then a detailed summary. "
                        "Use formatting suitable for Slack. "
                        "This means a single * for making titles bold. NEVER use ** for bolding text. "
                        "When formatting code blocks, use triple backticks without specifying the language name."
                    )},
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
    return tasks

def submit_klusterai_job(
    api_key: str,
    base_url: str,
    tasks: list,
    last_run_file: Path,
    file_name: str = "batch_input.jsonl"
) -> dict:
    """
    Submits a batch processing job to kluster.ai and monitors its completion.
    
    Args:
        api_key: Kluster.ai API key
        base_url: Kluster.ai base URL
        tasks: List of task dictionaries to process
        last_run_file: Path to the file storing last run timestamp
        file_name: Name of the temporary JSONL file to store tasks
    """
    # Save tasks to file
    with open(file_name, "w") as file:
        for task in tasks:
            file.write(json.dumps(task) + "\n")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )

    # Upload batch file
    batch_input_file = client.files.create(
        file=open(file_name, "rb"),
        purpose="batch"
    )
    print(f"Batch file uploaded. File id: {batch_input_file.id}")

    # Create batch request
    response = client.batches.create(
        input_file_id=batch_input_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    print(f"Batch request submitted. Batch ID: {response.id}")

    # Update the last run time
    update_last_run_time(last_run_file)
    
    # Monitor batch status
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

def save_results(batch_status, client) -> bool:
    """
    Saves the results of a completed batch job to a local file.
    
    Args:
        batch_status: Status object from the batch job
        client: OpenAI client instance
        
    Returns:
        bool: True if results were saved successfully, False otherwise
    """
    if batch_status.status.lower() == "completed":
        result_file_id = batch_status.output_file_id
        results = client.files.content(result_file_id).content
        
        result_file_name = "batch_results.jsonl"
        with open(result_file_name, "wb") as file:
            file.write(results)
        print(f"\nResults saved to {result_file_name}")
        return True
    else:
        print(f"Batch failed with status: {batch_status.status}")
        return False

def chunk_message(text: str, limit: int = 40000) -> list:
    """
    Splits a message into chunks that respect Slack's character limit.
    
    Args:
        text: Message text to split
        limit: Character limit per message (default 40000)
        
    Returns:
        list: List of message chunks
    """
    if len(text) <= limit:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Split by newlines to avoid breaking in middle of lines
    lines = text.split('\n')
    
    for line in lines:
        if len(current_chunk) + len(line) + 1 <= limit:
            current_chunk += line + '\n'
        else:
            # If current chunk is not empty, add it to chunks
            if current_chunk:
                chunks.append(current_chunk.rstrip())
            current_chunk = line + '\n'
    
    # Add the last chunk if not empty
    if current_chunk:
        chunks.append(current_chunk.rstrip())
    
    return chunks

def post_to_slack(channel: str, text: str, token: str):
    """
    Posts a message to a Slack channel, breaking into multiple messages if needed.
    
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
    
    # Split message into chunks if needed
    chunks = chunk_message(text)
    
    for chunk in chunks:
        data = {
            "channel": channel,
            "text": chunk,
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
            break  # Stop sending chunks if there's an error
        
        # Add a small delay between chunks to avoid rate limiting
        if len(chunks) > 1:
            time.sleep(1)

def process_and_post_results(
    org_name: str,
    slack_channel: str,
    slack_token: str
):
    """
    Processes batch results and posts them to Slack.
    
    Args:
        org_name: GitHub organization name
        slack_channel: Slack channel to post to
        slack_token: Slack API token
    """
    today_date = datetime.now().strftime("%B %d, %Y")
    issue_url_map = {}
    repo_results = {}
    
    # Create issue URL map
    with open("batch_input.jsonl", "r") as input_file:
        for line in input_file:
            task = json.loads(line)
            custom_id = task.get("custom_id", "N/A")
            metadata = task.get("metadata", {})
            issue_url_map[custom_id] = (
                metadata.get("issue_url", "No URL available"),
                metadata.get("title", ""),
                metadata.get("repo_name", "unknown")
            )
    
    # Process results and organize by repository
    with open("batch_results.jsonl", "r") as output_file:
        for line in output_file:
            result = json.loads(line)
            custom_id = result.get("custom_id", "N/A")
            response_content = result.get("response", {}).get("body", {}).get("choices", [{}])[0].get("message", {}).get("content", "No content available")
            issue_url, title, repo_name = issue_url_map.get(custom_id, ("No URL available", "No title available", "unknown"))
            
            if repo_name not in repo_results:
                repo_results[repo_name] = []
            
            repo_results[repo_name].append(f"*Title:* <{issue_url}|[{title}]>\n{response_content}\n")
    
    # Create combined message grouped by repository
    combined_message = f"*Latest Updates for {org_name} ({today_date})*\n\n"
    
    for repo_name, summaries in repo_results.items():
        combined_message += f"*Repository: {repo_name}*\n"
        combined_message += "".join(summaries)
        combined_message += "\n"
    
    # Split into chunks if necessary and post
    chunks = chunk_message(combined_message)
    for chunk in chunks:
        post_to_slack(slack_channel, chunk, slack_token)
    
    print(f"Results have been processed and posted to Slack channel {slack_channel}")

def main():
    parser = argparse.ArgumentParser(description='GitHub Issue Summarizer')
    parser.add_argument('--config', default='config.yaml',
                       help='Path to the YAML configuration file')
    parser.add_argument('--env', help='Path to the environment file (optional)')
    args = parser.parse_args()
    
    config = load_config(args.config, args.env)
    
    # Create last_run file path from config path
    last_run_file = Path(args.config).with_suffix('.last_run')
    
    issues = fetch_github_issues(
        github_token=config['github']['token'],
        owner=config['github']['owner'],
        repo=config['github']['repo'],
        last_run_file=last_run_file
    )
    
    if len(issues) == 0:
        print("No new issues to report")
        return
    
    tasks = prepare_klusterai_job(
        model=config['klusterai']['model'],
        github_token=config['github']['token'],
        input_token_limit=config['limits']['input_tokens'],
        issues=issues,
        tokenizer=tokenizer
    )
    
    batch_status = submit_klusterai_job(
        api_key=config['klusterai']['api_key'],
        base_url=config['klusterai']['base_url'],
        tasks=tasks,
        last_run_file=last_run_file
    )
    
    if batch_status.status.lower() == "completed":
        process_and_post_results(
            org_name=config['github']['owner'],
            slack_channel=config['slack']['channel'],
            slack_token=config['slack']['token']
        )

if __name__ == "__main__":
    main()



