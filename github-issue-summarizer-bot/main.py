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
    # If env_path is provided, use it directly
    if env_path:
        load_dotenv(env_path)
    else:
        # Use same name as config file but with .env extension
        env_file = Path(config_path).with_suffix('.env')
        load_dotenv(env_file)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    config['klusterai']['api_key'] = os.getenv("KLUSTERAI_API_KEY")
    config['github']['token'] = os.getenv("GH_TOKEN")
    config['slack']['token'] = os.getenv("SLACK_TOKEN")
    
    return config

CONFIG = load_config()

# Lets leave some room for output tokens
INPUT_TOKEN_LIMIT = CONFIG['limits']['input_tokens_per_request']

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

def get_last_run_time() -> datetime:
    """
    Retrieves the timestamp of the last successful run.
    
    Returns:
        datetime: Timestamp of last run, or 24 hours ago if no record exists
    """
    try:
        with open('.last_run', 'r') as f:
            timestamp = float(f.read().strip())
            return datetime.fromtimestamp(timestamp)
    except (FileNotFoundError, ValueError):
        # If file doesn't exist or is invalid, default to 24 hours ago
        return datetime.now() - timedelta(days=1)

def update_last_run_time():
    with open('.last_run', 'w') as f:
        f.write(str(time.time()))

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

def fetch_issue_comments(comments_url: str, headers: dict, tokenizer) -> str:
    """
    Retrieves and concatenates comments for a GitHub issue, respecting token limits.
    
    Args:
        comments_url: URL endpoint for the issue's comments
        headers: Request headers including authentication
        tokenizer: Tokenizer instance for calculating token counts
        
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
        
        if current_tokens + new_comment_tokens > INPUT_TOKEN_LIMIT:
            print("Token limit reached for comments.")
            break
        
        if comments_text:
            comments_text += "\n---\n"
        comments_text += comment_body
    
    return comments_text

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

def submit_klusterai_job(tasks: list, file_name: str = "batch_input.jsonl"):
    """
    Submits a batch processing job to kluster.ai and monitors its completion.
    
    Args:
        tasks: List of task dictionaries to process
        file_name: Name of the temporary JSONL file to store tasks
        
    Returns:
        BatchStatus: Object containing the final status of the batch job
    """
    # Save tasks to file
    with open(file_name, "w") as file:
        for task in tasks:
            file.write(json.dumps(task) + "\n")

    client = OpenAI(
        api_key=CONFIG['klusterai']['api_key'],
        base_url=CONFIG['klusterai']['base_url']
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

    # so we know when the last issues in this batch were processed
    update_last_run_time() 

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

def process_and_post_results():
    """
    Processes batch results and posts them to Slack.
    
    Reads the batch input and output files, matches results with their
    corresponding GitHub issues, and posts formatted summaries to Slack.
    Each issue is posted as a separate message with its title and URL.
    """
    today_date = datetime.now().strftime("%B %d, %Y")
    issue_url_map = {}
    
    # Create issue URL map
    with open("batch_input.jsonl", "r") as input_file:
        for line in input_file:
            task = json.loads(line)
            custom_id = task.get("custom_id", "N/A")
            issue_url = task.get("metadata", {}).get("issue_url", "No URL available")
            title = task.get("metadata", {}).get("title", "")
            issue_url_map[custom_id] = (issue_url, title)
    
    # Post title to Slack
    post_to_slack(
        CONFIG['slack']['channel'], 
        f"*Latest {CONFIG['github']['repo']} Updates ({today_date})*", 
        CONFIG['slack']['token']
    )
    
    # Process results and post each one
    with open("batch_results.jsonl", "r") as output_file:
        for line in output_file:
            result = json.loads(line)
            custom_id = result.get("custom_id", "N/A")
            response_content = result.get("response", {}).get("body", {}).get("choices", [{}])[0].get("message", {}).get("content", "No content available")
            issue_url, title = issue_url_map.get(custom_id, ("No URL available", "No title available"))
            
            formatted_result = f"*Title:* <{issue_url}|[{title}]>\n{response_content}\n\n"
            post_to_slack(CONFIG['slack']['channel'], formatted_result, CONFIG['slack']['token'])
    
    print(f"Results have been processed and posted to Slack channel {CONFIG['slack']['channel']}")

def main():
    parser = argparse.ArgumentParser(description='GitHub Issue Summarizer')
    parser.add_argument('--config', 
                       default='config.yaml',
                       help='Path to the YAML configuration file')
    parser.add_argument('--env',
                       help='Path to the environment file (optional)')
    args = parser.parse_args()
    
    # Load config based on provided paths
    global CONFIG
    CONFIG = load_config(args.config, args.env)
    
    # get latest GitHub issues
    issues = fetch_github_issues()
    if len(issues) == 0:
        print("No new issues to report")
        return
    
    # prepare batch job
    tasks = prepare_klusterai_job(issues, tokenizer)
    
    # submit batch job
    batch_status = submit_klusterai_job(tasks)
    
    # process results and post to slack
    if batch_status.status.lower() == "completed":
        process_and_post_results()

if __name__ == "__main__":
    main()



