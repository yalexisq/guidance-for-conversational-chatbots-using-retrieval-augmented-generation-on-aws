from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Config:
    DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
    DOCUMENTS_TABLE_NAME = os.environ['DOCUMENTS_TABLE_NAME']
    KENDRA_INDEX = os.environ['KENDRA_INDEX']
    KENDRA_REGION = os.environ['KENDRA_REGION']
    MODEL_ENDPOINT = os.environ['MODEL_ENDPOINT']
    API_KEYS_ANTHROPIC_NAME =os.environ['API_KEYS_ANTHROPIC_NAME']
    ADMIN_USERNAMES = os.environ.get('ADMIN_USERNAMES', '')
    ADMIN_PASSCODE = os.environ.get('ADMIN_PASSCODE', '')
    
config = Config()
