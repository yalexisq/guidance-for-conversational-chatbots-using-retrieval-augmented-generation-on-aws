#helper.py
import logging
import json
import pprint
import config
import re
import os
import boto3
import uuid
from datetime import datetime, timezone

from memory import chatMemory
from langchain import SagemakerEndpoint
from langchain.llms.sagemaker_endpoint import ContentHandlerBase
from typing import Any, Optional ,Dict
from langchain.llms import Anthropic

logger = logging.getLogger()
logger.setLevel(logging.INFO)

#####################
#This code is usefull to handle input and output from Sagemaker endpoint

class ContentHandler(ContentHandlerBase):
    content_type = "application/json"
    accepts = "application/json"

    def transform_input(self, prompt: str, model_kwargs: Dict) -> bytes:
        input_str = json.dumps({ "prompt" : prompt, **model_kwargs})
        return input_str.encode('utf-8')
    
    def transform_output(self, output: bytes) -> str:
        response_json = json.loads(output.read().decode("utf-8"))
        #response_json = output.read().decode("utf-8")
        return response_json["completions"][0]['data']['text']

content_handler = ContentHandler()

######################

def close(intent_request,session_attributes,fulfillment_state, message):

    response = {
                    'sessionState': {
                        'sessionAttributes': session_attributes,
                		'dialogAction': {
                            'type': 'Close'
                        },
                        'intent': intent_request['sessionState']['intent']
                        },
                    'messages': [message],
                    'sessionId': intent_request['sessionId']
                }
    response['sessionState']['intent']['state'] = fulfillment_state
    
    #if 'requestAttributes' in intent_request :
    #    response['requestAttributes']   =  intent_request["requestAttributes"]
        
    logger.info('<<help_desk_bot>> "Lambda fulfillment function response = \n' + pprint.pformat(response, indent=4)) 

    return response

def get_user_message(event):
    return event['transcriptions'][0]['transcription']
    
def get_sessionid(event):
    return event['sessionId']

def is_http_request(event):
    return 'headers' in event

def create_presigned_url(bucket_name, object_name, expiration=120):
    # Choose AWS CLI profile, If not mentioned, it would take default
    #boto3.setup_default_session(profile_name='personal')
    # Generate a presigned URL for the S3 object
    #s3_client = boto3.client('s3',region_name="us-east-1",config=boto3.session.Config(signature_version='s3v4',))
    s3_client = boto3.client('s3',region_name="us-east-1")
    try:
        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': bucket_name,
                                                            'Key': object_name},
                                                    ExpiresIn=expiration)
    except Exception as e:
        print(e)
        logging.error(e)
        return "Error"
    # The response contains the presigned URL
    print(response)
    return response

def url_parser(text):
    match = re.search(r'\[source\s*:\s*(?P<url>[^\]]+)\s*\]$',text)
    if match:
        url =match.group('url').strip()
        if url.startswith('s3://'):
            
            s3 = boto3.client('s3')
            bucket_name ,key = url[len('s3://'):].split('/',1)
            #signed_url =s3.generate_presigned_url()
            
            signed_url = create_presigned_url(bucket_name,key)
            #signed_url = url
            file_name = os.path.basename(key)
            return text[:match.start()],signed_url,file_name
            
            
        else:
            return text[:match.start()],None,None
    else:
        return text,None,None


def clear_history(event):
    sessionId =get_sessionid(event)
    chatMemory(sessionId).clear_DynamoDBChatMessageHistory()
    return "conversation history cleared"

def get_slot_value(intent_request, slot_name):
    slots = intent_request.get('sessionState', {}).get('intent', {}).get('slots', {}) or {}
    slot = slots.get(slot_name) or {}
    if not slot:
        return None
    if isinstance(slot, dict):
        value = slot.get('value', {})
        if isinstance(value, dict):
            return value.get('interpretedValue') or value.get('originalValue')
    return None

def get_document_table():
    dynamodb = boto3.resource('dynamodb')
    return dynamodb.Table(config.config.DOCUMENTS_TABLE_NAME)

def get_allowed_admins():
    raw = config.config.ADMIN_USERNAMES
    return {name.strip().lower() for name in raw.split(',') if name.strip()}

def validate_admin(username, passcode):
    if not username:
        return False, "Please provide your admin username."
    allowed = get_allowed_admins()
    if allowed and username.lower() not in allowed:
        return False, "You are not authorized to access admin features."
    if config.config.ADMIN_PASSCODE and passcode != config.config.ADMIN_PASSCODE:
        return False, "Invalid admin passcode."
    return True, "Admin access granted."

def store_document(title, category, content, uploaded_by):
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    table = get_document_table()
    table.put_item(
        Item={
            "doc_id": doc_id,
            "title": title,
            "category": category,
            "content": content,
            "uploaded_by": uploaded_by,
            "created_at": now,
        }
    )
    return doc_id

def normalize_terms(text):
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return [term for term in cleaned.split() if len(term) > 2]

def retrieve_documents(query, limit=3):
    table = get_document_table()
    items = []
    response = table.scan(
        ProjectionExpression="doc_id, title, category, content, created_at"
    )
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.scan(
            ProjectionExpression="doc_id, title, category, content, created_at",
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    terms = normalize_terms(query)
    scored = []
    for item in items:
        content = f"{item.get('title', '')} {item.get('content', '')}".lower()
        score = sum(1 for term in terms if term in content)
        scored.append((score, item))

    scored.sort(key=lambda entry: (entry[0], entry[1].get("created_at", "")), reverse=True)
    filtered = [item for score, item in scored if score > 0]
    if not filtered:
        filtered = [item for _, item in scored]
    return filtered[:limit]

def format_history(memory):
    history = memory.load_memory_variables({}).get("history", [])
    lines = []
    for message in history:
        role = "User" if message.type == "human" else "Assistant"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)

#AI handler
def AI_handler(event):
    #print('printing Event : ',event)
    user_message = get_user_message(event)
    sessionId= get_sessionid(event)
    
    llm = Anthropic(
        #config.config.MODEL_ENDPOINT
        anthropic_api_key=config.config.API_KEYS_ANTHROPIC_NAME,
        temperature=0
    )
    
    memory = chatMemory(sessionId).memory
    documents = retrieve_documents(user_message, limit=3)
    history_text = format_history(memory)
    if documents:
        docs_text = "\n\n".join(
            [
                f"Document {index + 1} ({doc.get('category', 'General')}): "
                f"{doc.get('title', 'Untitled')}\n{doc.get('content', '')}"
                for index, doc in enumerate(documents)
            ]
        )
    else:
        docs_text = "No documents available."

    prompt = (
        "You are an internal assistant that answers questions using only the provided "
        "SOP and HR documents. If the answer is not contained in the documents, say you "
        "do not have that information. Provide a concise answer and end with a line in "
        "this format: Sources: <title> (<doc_id>), <title> (<doc_id>).\n\n"
        f"Conversation history:\n{history_text}\n\n"
        f"Documents:\n{docs_text}\n\n"
        f"Question: {user_message}\nAnswer:"
    )
    response = llm.predict(prompt)
    if documents:
        sources = ", ".join(
            [
                f"{doc.get('title', 'Untitled')} ({doc.get('doc_id')})"
                for doc in documents
            ]
        )
        response = f"{response}\nSources: {sources}"
    return url_parser(response)

