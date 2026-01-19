#AI Handler
import logging
import json
import helpers

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_session_attributes(intent_request):
    sessionState = intent_request['sessionState']
    if 'sessionAttributes' in sessionState:
        return sessionState['sessionAttributes']
    return {}

def hello_intent_handler(intent_request, session_attributes):
    # clear out session attributes to start new
    session_attributes = {}

    response_string = "Hello! How can we help you today?"
    return helpers.close(intent_request,session_attributes, 'Fulfilled', {'contentType': 'PlainText','content': response_string})   

def goodbye_intent_handler(intent_request, session_attributes):
    # clear out session attributes to start over
    session_attributes = {}
    response_string = "Thanks! Have a great rest of your day."
    return helpers.close(session_attributes, 'Fulfilled', {'contentType': 'PlainText','content': response_string})   

def fallback_intent_handler(intent_request, session_attributes):
    session_attributes['fallbackCount'] = '0'
    #fallbackCount = helpers.increment_counter(session_attributes, 'fallbackCount')

    kendra_agent_message,url,fileName = helpers.AI_handler(intent_request)

    if kendra_agent_message is None:
        response = "Sorry, I was not able to understand your question."
        return helpers.close(intent_request,session_attributes,'Fulfilled', {'contentType': 'PlainText','content': response})
    else:
        logger.debug('<<help_desk_bot>> "fallback_intent_handler(): kendra_response = %s', kendra_agent_message)
        
        if (url==None) or (url=='conversation history') or (fileName==None):
            #markup ="""<p>"""+ kendra_agent_message+""" [source: conversation history/LLM] </p>"""
            markup ="""<p>"""+ kendra_agent_message+"""</p>"""
            return helpers.close(intent_request,session_attributes, 'Fulfilled', {'contentType': 'CustomPayload','content': markup})
        else:
            markup ="""<p>"""+ kendra_agent_message+""" [source: <a href='"""+url+"""' target='_blank'> """+fileName+""" </a> ]</p>"""
            return helpers.close(intent_request,session_attributes, 'Fulfilled', {'contentType': 'CustomPayload','content': markup})

def standard_question_intent_handler(intent_request, session_attributes):
    session_attributes['fallbackCount'] = '0'

    kendra_agent_message,url,fileName = helpers.AI_handler(intent_request)

    if kendra_agent_message is None:
        response = "Sorry, I was not able to understand your question."
        return helpers.close(intent_request,session_attributes,'Fulfilled', {'contentType': 'PlainText','content': response})
    else:
        logger.debug('<<help_desk_bot>> "fallback_intent_handler(): kendra_response = %s', kendra_agent_message)
        
        if (url==None) or (url=='conversation history') or (fileName==None):
            #markup ="""<p>"""+ kendra_agent_message+""" [source: conversation history/LLM] </p>"""
            markup ="""<p>"""+ kendra_agent_message+"""</p>"""
            return helpers.close(intent_request,session_attributes, 'Fulfilled', {'contentType': 'CustomPayload','content': markup})
        else:
            markup ="""<p>"""+ kendra_agent_message+""" [source: <a href='"""+url+"""' target='_blank'> """+fileName+""" </a> ]</p>"""
            return helpers.close(intent_request,session_attributes, 'Fulfilled', {'contentType': 'CustomPayload','content': markup})

def clear_history_intent_handler(intent_request, session_attributes):
    # clear out session attributes to start over
    session_attributes = {}
    response_string = helpers.clear_history(intent_request)
    return helpers.close(intent_request,session_attributes, 'Fulfilled', {'contentType': 'PlainText','content': response_string})   

def admin_login_intent_handler(intent_request, session_attributes):
    username = helpers.get_slot_value(intent_request, "username")
    passcode = helpers.get_slot_value(intent_request, "passcode")
    is_valid, message = helpers.validate_admin(username, passcode)
    if is_valid:
        session_attributes["isAdmin"] = "true"
        session_attributes["adminUser"] = username
    else:
        session_attributes["isAdmin"] = "false"
    return helpers.close(intent_request, session_attributes, 'Fulfilled', {'contentType': 'PlainText','content': message})

def admin_add_document_intent_handler(intent_request, session_attributes):
    if session_attributes.get("isAdmin") != "true":
        response_string = "Admin access required. Please log in as an admin to add documents."
        return helpers.close(intent_request, session_attributes, 'Fulfilled', {'contentType': 'PlainText','content': response_string})

    title = helpers.get_slot_value(intent_request, "title")
    category = helpers.get_slot_value(intent_request, "category") or "General"
    content = helpers.get_slot_value(intent_request, "content")
    if not title or not content:
        response_string = "Please provide both a document title and content."
        return helpers.close(intent_request, session_attributes, 'Fulfilled', {'contentType': 'PlainText','content': response_string})

    doc_id = helpers.store_document(
        title=title,
        category=category,
        content=content,
        uploaded_by=session_attributes.get("adminUser", "unknown"),
    )
    response_string = f"Document added successfully with ID {doc_id}."
    return helpers.close(intent_request, session_attributes, 'Fulfilled', {'contentType': 'PlainText','content': response_string})

# list of intent handler functions for the dispatch proccess
HANDLERS = {
    'chatbot_hello':            {'handler': hello_intent_handler},
    'help_desk_goodbye':        {'handler': goodbye_intent_handler},
    'standard_question_intent': {'handler': standard_question_intent_handler},
    'clearhistoryIntent':       {'handler': clear_history_intent_handler},
    'admin_login':              {'handler': admin_login_intent_handler},
    'admin_add_document':       {'handler': admin_add_document_intent_handler}
    #'FallbackIntent':         {'handler': fallback_intent_handler},
}

def lambda_handler(event, context):
    logger.info('<help_desk_bot>> Lex event info = ' + json.dumps(event))

    session_attributes = get_session_attributes(event)

    logger.debug('<<help_desk_bot> lambda_handler: session_attributes = ' + json.dumps(session_attributes))
    
    currentIntent = event['sessionState']['intent']['name']
    
    if currentIntent is None:
        response_string = 'Sorry, I didn\'t understand.'
        return helpers.close(session_attributes,currentIntent, 'Fulfilled', {'contentType': 'PlainText','content': response_string})
    intentName = currentIntent
    if intentName is None:
        response_string = 'Sorry, I didn\'t understand.'
        return helpers.close(session_attributes,intentName, 'Fulfilled', {'contentType': 'PlainText','content': response_string})

    # see HANDLERS dict at bottom
    if HANDLERS.get(intentName, False):
        return HANDLERS[intentName]['handler'](event, session_attributes)   # dispatch to the event handler
    else:
        response_string = "The intent " + intentName + " is not yet supported."
        return helpers.close(session_attributes,intentName, 'Fulfilled', {'contentType': 'PlainText','content': response_string})
