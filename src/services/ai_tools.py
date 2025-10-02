# In src/services/ai_tools.py

# --- Tool Definitions (Formatted for Google's Gemini API) ---

UPDATED_STATE_SCHEMA = {
    "type": "object",
    "description": "OPTIONAL: The full, updated conversation state object to be persisted for the next turn."
}

continue_conversation = {
    "name": "continue_conversation",
    "description": "The default tool for all standard conversational replies. Use this to ask questions, answer questions, and guide the user, while updating the conversational state.",
    "parameters": {
        "type": "object",
        "properties": {
            "reply_suggestion": {"type": "string"},
            "updated_state": UPDATED_STATE_SCHEMA
        },
        "required": ["reply_suggestion", "updated_state"]
    }
}

# answer_inquiry = {
#     "name": "answer_inquiry",
#     "description": "The default tool for all conversational replies. Use this to answer questions, greet users, and ask clarifying questions. It is MANDATORY to extract any entities you identify (like a service name, date, or customer name) into the appropriate parameters.",
#     "parameters": {
#         "type": "object",
#         "properties": {
#              "reply_suggestion": {
#                 "type": "string",
#                 "description": "A friendly, helpful, and direct answer to the user's question, based on the provided context. The reply MUST end with a helpful follow-up question."
#             },
#              "service": {
#                 "type": "string",
#                 "description": "The specific service the user is asking about, if any. This MUST be extracted if mentioned."
#             },
#             "updated_state": UPDATED_STATE_SCHEMA
#         },
#         "required": ["reply_suggestion", "service", "updated_state"]
#     }
# }

# request_booking_confirmation = {
#     "name": "request_booking_confirmation",
#     "description": "Use this when a user has provided all necessary details (service, date, time) for a booking for the first time. This tool asks for the user's final confirmation before the booking is made.",
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "service": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"},
#             "reply_suggestion": {"type": "string", "description": "A summary of the booking details asking for confirmation."},
#             "updated_state": UPDATED_STATE_SCHEMA
#         },
#         "required": ["service", "date", "time", "reply_suggestion", "updated_state"]
#     }
# }

create_booking = {
    "name": "create_booking",
    "description": "Use this ONLY when a user has explicitly confirmed a pending booking request (e.g., they say 'yes', 'confirm', 'that's correct').",
    "parameters": {
        "type": "object",
        "properties": {
            "service": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"},
            "updated_state": UPDATED_STATE_SCHEMA
        },
        "required": ["service", "date", "time", "updated_state"]
    }
}

schedule_lead_follow_up = {
    "name": "schedule_lead_follow_up",
    "description": "Use this if a user showed clear booking intent but then hesitated, got distracted, or ended the conversation before confirming. This schedules a 24-hour follow-up.",
    "parameters": {
        "type": "object",
        "properties": {
            "reply_suggestion": {"type": "string", "description": "A polite, understanding reply to the user's hesitation."},
            "service": {"type": "string", "description": "The service they were about to book, if known."},
            "updated_state": UPDATED_STATE_SCHEMA
        },
        "required": ["reply_suggestion", "updated_state"]
    }
}

handoff_to_human = {
    "name": "handoff_to_human",
    "description": "Use this as a safety net when the user is frustrated, confused, asks for a human, or the request is too complex to handle.",
    "parameters": { 
        "type": "object", 
        "properties": { 
            "reason": {"type": "string"},
            "updated_state": UPDATED_STATE_SCHEMA
        }, 
        "required": ["reason", "updated_state"] 
    }
}

capture_customer_name = {
    "name": "capture_customer_name",
    "description": "Use this tool ONLY when a user provides their name in response to being asked for it.",
    "parameters": {
        "type": "object",
        "properties": {
            "customer_name": {"type": "string"},
            "reply_suggestion": {"type": "string"},
            "updated_state": UPDATED_STATE_SCHEMA
        },
        "required": ["customer_name", "reply_suggestion", "updated_state"]
    }
}

update_booking = {
    "name": "update_booking",
    "description": "Use this tool to modify an existing appointment. This handles changes to the service, the time, the date, or any combination of these. You MUST infer the original service name from the booking history context.",
    "parameters": {
        "type": "object",
        "properties": {
            "original_service_name": {
                "type": "string",
                "description": "The service name of the booking to be changed, inferred from the conversation history."
            },
            "new_service_name": {
                "type": "string",
                "description": "OPTIONAL: The name of the NEW service the user is requesting."
            },
            "new_date": {
                "type": "string",
                "description": "OPTIONAL: The NEW date the user wants, resolved to YYYY-MM-DD format."
            },
            "new_time": {
                "type": "string",
                "description": "OPTIONAL: The NEW time the user wants, resolved to HH:MM format."
            },
            "reply_suggestion": {
                "type": "string",
                "description": "A polite, helpful reply confirming the requested change and asking for follow-up if needed."
            },
            "updated_state": UPDATED_STATE_SCHEMA
        },
        "required": ["original_service_name", "reply_suggestion", "updated_state"]
    }
}

process_reconciliation = {
    "name": "process_reconciliation",
    "description": "Parses a manager's daily delivery reconciliation message to extract which deliveries were confirmed and which failed.",
    "parameters": {
        "type": "object",
        "properties": {
            "confirmed_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "A list of all delivery IDs that the manager has marked as successful, confirmed, or 'OK'."
            },
            "failed_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "A list of all delivery IDs that the manager has marked as failed, not done, or 'FAIL'."
            }
        },
        "required": ["confirmed_ids", "failed_ids"]
    }
}

# greet_user = {
#     "name": "greet_user",
#     "description": "Use this tool ONLY as the very first response to a new customer who sends a simple greeting (e.g., 'Hi', 'Hello'). Your reply should welcome them and ask for their name.",
#     "parameters": {
#         "type": "object",
#         "properties": {
#              "reply_suggestion": {
#                 "type": "string",
#                 "description": "A welcoming greeting that politely asks for the user's name to begin the onboarding process."
#             }
#         },
#         "required": ["reply_suggestion"]
#     }
# }


RECONCILIATION_TOOLBOX = [{
    "function_declarations": [
        process_reconciliation,
    ]
}]

AI_TOOLBOX = [{
    "function_declarations": [
        continue_conversation, # The new primary tool
        capture_customer_name,
        update_booking,
        create_booking,
        schedule_lead_follow_up,
        handoff_to_human,
    ]
}]