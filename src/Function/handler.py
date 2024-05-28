from youtube_transcript_api import YouTubeTranscriptApi
import json
import boto3
from botocore.exceptions import ClientError
import os
import requests
from botocore.config import Config
import re

# get sns topic name from environment variables
topic_name = os.environ['SENDTRANSCRIPTTOPIC_TOPIC_NAME']
topic_arn = os.environ['SENDTRANSCRIPTTOPIC_TOPIC_ARN']
words_cutoff = 4000

# send message to sns topic
def send_message(topic_arn, subject, message):
    sns = boto3.resource('sns')
    topic = sns.Topic(topic_arn)
    response = topic.publish(
        Message=message,
        Subject=subject,
        MessageStructure='string'
    )

def reshape_text(prompt, topic_to_highlight="machine learning"):
    print("original prompt length (bytes): {}".format(len(prompt)))
    shortened_prompt = ""
    for word in prompt.split()[:words_cutoff]:
        shortened_prompt = shortened_prompt + " " + word
    prompt = shortened_prompt
    config = Config(read_timeout=1000)
    bedrock = boto3.client(service_name='bedrock-runtime', region_name='us-east-1', config=config)
    #command = "Insert punctuation and paragraphs in the following text. Output format is markdown. Highlight keywords that are related to "+topic_to_highlight+" using bold font."
    command = "Insert punctuation and paragraphs in the following text."
    enclosed_prompt = "Human: " + command + " " + prompt + ".\n\nAssistant:"
    # print("enclosed_prompt: {}".format(enclosed_prompt))
    print("shortened prompt length (bytes): {}".format(len(prompt)))
    words = len(prompt.split())
    print("shortened prompt length (words): {}".format(words))
    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "temperature": 1,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text":enclosed_prompt
                        }
                    ]
                }
            ]
        }
    )
    modelId = 'anthropic.claude-3-haiku-20240307-v1:0'
    accept = 'application/json'
    contentType = 'application/json'
    response = bedrock.invoke_model(body=body, modelId=modelId, accept=accept, contentType=contentType)
    response_body = json.loads(response.get('body').read())
    answer = response_body["content"][0]["text"]
    words = len(answer.split())
    print("LLM response length (bytes): {}".format(len(answer)))
    print("LLM response length (words): {}".format(words))
    print("answer: {}".format(answer))
    return answer

def get_video_transcript(video_id):
    video_id = video_id[-11:]
    response=YouTubeTranscriptApi.get_transcript(video_id) 
    contents=""
    for r in response:
        for k, v in r.items():
            if k == "text":
                contents=contents+" "+v
    return contents

def get_html_title(video_id):
    headers = {'headers':'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:51.0) Gecko/20100101 Firefox/51.0'}
    n = requests.get('https://www.youtube.com/watch?v='+video_id, headers=headers)
    al = n.text
    html_title = al[al.find('<title>') + 7 : al.find('</title>')]
    channel_name = re.search(r'"channelName":"([^"]*)"', al)
    if channel_name:
        print("channel name: {}".format(channel_name.group(1)))
    else:
        print("Channel name not found.")
    # cut " - YouTube" postfix from title (10 letters)
    return html_title[:-10]

def handler(event, context):
    print("event: {}".format(event))
    # extract sns message subject
    text = event['Records'][0]['Sns']['Message']
    topic_to_highlight = "machine learning"
    print("video_id: {}".format(text))
    if len(text) == 11:
        video_id=text
        transcript = get_video_transcript(video_id)
        video_title = get_html_title(video_id)
        llm_output = reshape_text(transcript, topic_to_highlight)
        llm_output = "Video link: https://www.youtube.com/watch?v="+video_id+"\n" + llm_output
    else:
        llm_output = "(empty)"
        video_title="(invalid video_id)"
    title = "Transcript from video \""+video_title+"\""
    title = title[:96]
    print("title: {}".format(title))
    send_message(topic_arn, title, llm_output)

    return {
        'statusCode': 200,
        'body': json.dumps(llm_output)
    }
