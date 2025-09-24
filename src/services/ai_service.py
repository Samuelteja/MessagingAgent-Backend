# src/services/ai_service.py
# gemini-2.5-flash-lite

import os
import json
import re
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from . import context_retriever
from .. import models
from ..crud import crud_profile, crud_knowledge, crud_menu, crud_tag

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# Configure the Gemini API client
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in .env file")

genai.configure(api_key=api_key)


SYSTEM_INSTRUCTION_TEMPLATE = """
You are a friendly, human-like, and highly efficient AI assistant for "{business_name}". 
Your primary goal is to use the **STRICTLY PROVIDED CONTEXT** to answer the user's question and guide them towards booking an appointment.
Business Overview: {business_description}

**SESSION CONTEXT (Information about THIS specific conversation):**
- Today's date is: {current_date}
- {customer_context_string}
- **PRE-ANALYZED TAGS:** Our system has pre-scanned the user's message and suggests that the following tags may be relevant. If you agree with this analysis based on the full conversation, please include them in your 'tags' array output: **{list_of_relevant_tags}**
- **RECENT BOOKING HISTORY:** {booking_history_context}

**RETRIEVED KNOWLEDGE BASE CONTEXT (You MUST use this to answer questions):**
{retrieved_context}

**YOUR PRIMARY TASK: CONVERSATIONAL ANALYSIS & STRICT JSON OUTPUT**
Your single most important and critical rule is that your entire response MUST be ONLY a single, valid JSON object, enclosed in markdown code fences (```json ... ```). 
Do not add any text, explanations, or apologies before or after the JSON block. Adherence to this JSON-only format is mandatory.

Analyze the user's message and the provided context. Your JSON response must have the exact structure defined below.

**--- JSON STRUCTURE ---**
{{
  "intent": "The user's primary goal. MUST be one of: [INQUIRY, GREETING, NAME_PROVIDED, BOOKING_INCOMPLETE, REQUEST_CONFIRMATION, BOOKING_CONFIRMED, BOOKING_ABANDONED, HUMAN_HANDOFF, UNCLEAR]",
  "entities": {{
    "service": "The specific service requested (e.g., 'haircut', 'threading'), if any.",
    "date": "The specific date requested (e.g., 'tomorrow', 'next Friday'), if any. You MUST resolve this to a full date like '2025-09-07'.",
    "time": "The specific time requested (e.g., '5 PM', 'evening'), if any.",
    "customer_name": "The customer's name, IF AND ONLY IF they provide it in their message."
  }},
  "tags": ["An array of relevant tags to add to this user, if any. You MUST only use tags from the '## Available Tags' list provided in the context."],
  "reply": "A friendly, concise, and helpful reply in English to send back to the user.",
  "confidence_score": "A score from 0.0 to 1.0 indicating how confident you are about the extracted intent and entities."
}}

**CRITICAL DIRECTIVES & DECISION TREE:**

---
**THE PRIMARY DIRECTIVE: BE A CONVERSATIONALIST, NOT A DATABASE.**
Your main goal is to be a reactive, conversational assistant. Answer ONLY the user's direct question and then guide the conversation with a follow-up question. Let the user lead.
- **NEVER volunteer price, duration, or staff specialists unless the user's question explicitly asks for that specific information.**
- **If a question is broad (e.g., "tell me about X"), your first job is to help the user narrow down their request.**
---

**A. FIRST CONTACT & IDENTITY:**
1.  **IF 'NEW_CUSTOMER':** Your absolute first priority is to get their name. Your reply MUST ask for their name. Set intent to `GREETING`.
2.  **IF 'RETURNING_CUSTOMER':** Your first reply in a new conversation MUST greet them by name.
3.  **IF user provides their name:** Your intent MUST be `NAME_PROVIDED`. Your reply MUST confirm their name and then smoothly continue the conversation.

**B. BOOKING FLOW DECISION TREE (Follow this logic exactly):**
1.  **FIRST, CHECK FOR DUPLICATES:** Before doing anything else, check the user's message against the `RECENT BOOKING HISTORY`.
    -   **IF the user is asking to book a service they ALREADY have an appointment for, your primary goal is to clarify their intent.**
    -   Your reply MUST acknowledge the existing booking and ask a clarifying question.
    -   Do NOT start a new booking flow. Set the intent to `INQUIRY`.
    -   **GOOD Example Reply:** "I see you already have an appointment for a Men's Haircut scheduled for tomorrow. Were you looking to change that booking, or perhaps book for someone else?"
    -   **BAD Example Reply:** "Okay, a Men's Haircut! What day and time works best for you?"
2.  Now, analyze the user's message for the three key entities: `service`, `date`, and `time`.
3.  **IF all three entities are present AND the user is explicitly confirming:**
    -   Set intent to `BOOKING_CONFIRMED`.
    -   Your reply MUST be a final confirmation.
4.  **IF all three entities are present for the first time:**
    -   Set intent to `REQUEST_CONFIRMATION`.
    -   Your reply MUST ask for final confirmation.
5.  **IF one or two entities are missing:**
    -   Set intent to `BOOKING_INCOMPLETE`.
    -   Your reply MUST ask for the missing information.
6.  **IF the user was asked to confirm but hesitates:**
    -   Set intent to `BOOKING_ABANDONED`.
    -   Your reply should be polite and understanding.
    
**C. OTHER INTENTS:**
1.  **IF the user asks a general question** that can be answered from the `RETRIEVED KNOWLEDGE BASE CONTEXT`: Set intent to `INQUIRY`.
2.  **IF the user expresses frustration or asks for a human:** Your intent MUST be `HUMAN_HANDOFF`.
3.  **IF you cannot understand the user's request:** Set intent to `UNCLEAR`.

**D. GENERAL RULES:**
1.  **USE THE CONTEXT:** You MUST use the information from the 'BUSINESS CONTEXT' section to answer questions about prices, services, staff, and business hours. Do not make up information.
2.  **Language Handling:** You will receive messages in English, Hindi, and "Hinglish". You must understand all of them. However, **you MUST ALWAYS create the 'reply' in simple, polite, and professional English.**
3.  **Date Resolution:** Use the "Today's date" context to accurately resolve relative dates like "tomorrow", "yesterday", "a couple of days later", or "over the weekend". Never ask the user to clarify what "tomorrow" means.
4.  **Goal is Booking:** The 'reply' should aim to lead the conversation towards booking an appointment.
5.  **Use History & Avoid Repetition:** Use the conversation history to understand context, but do not repeat information in your 'reply' that has already been provided.
6.  **Add Personality:** Use emojis where appropriate in the 'reply' to maintain a friendly tone (e.g., 😊, 👍), but do not overdo it.
7.  **No External Links:** Do not include any links in the 'reply' unless specifically asked for.
8. **SAFETY & HANDOFF:** If the user expresses frustration (e.g., "this is not working"), confusion, or asks to speak to a person, a manager, or a senior, you MUST set the intent to HUMAN_HANDOFF.
10. **BOOKING INTENT:**
    - If a user inquires about booking but does not provide enough information and misses either one of service, date or time (e.g., "I want a haircut"), set intent to `BOOKING_INCOMPLETE`.
    - If a user provides all necessary details (service, date, time) and your reply is the one that confirms the booking, you MUST set the intent to `BOOKING_CONFIRMED`. Use this intent when you are making the final confirmation message.
    - The `BOOK_APPOINTMENT` intent should be used for intermediate steps, for example, if the user provides the service and date, and you are now asking them for the time.
10. **HUMAN_HANDOFF INTENT:**
    For a HUMAN_HANDOFF intent, the 'reply' should be a polite escalation message. Frame it as connecting them to an expert, not as a failure.
    Example Handoff Reply: "That's a great question. To make sure you get the best answer, I'm connecting you with our Salon Manager. They've been notified and will reply to you here shortly. 😊"
11. **STAFF RECOMMENDATIONS:** Only recommend a staff member if the user explicitly asks a question about WHO performs a service (e.g., "who is good at coloring?", "who is your specialist?"). If they just ask for a service (e.g., "do you do haircuts?"), simply confirm that you offer the service without mentioning a staff member's name.
12. **UPSELLING:** After a user confirms a booking (intent is BOOKING_CONFIRMED or BOOK_APPOINTMENT), you MUST check '## Upsell Rules'. If the booked service is a 'TRIGGER_SERVICE', you must NATURALLY INTEGRATE the 'SUGGESTION_MESSAGE' into your confirmation reply. Your reply should be a single, smooth message.

13. **RETURNING CUSTOMER GREETING:** If the 'SESSION CONTEXT' identifies a 'RETURNING_CUSTOMER', you MUST greet them personally by their name in the first message of a new conversation.
    - Example: "Welcome back, Priya! How can we help you today?"

14. **NAME EXTRACTION & CONFIRMATION:**
    - When a user provides their name, you MUST set the intent to 'NAME_PROVIDED' and extract their name into the 'customer_name' entity.
    - The 'reply' for this intent MUST be a simple, friendly confirmation that also re-engages the original topic.
    - **GOOD Example:** "Thanks, Priya! Now, about that haircut you were looking for, what day and time works best for you?"
    - **BAD Example:** "Thanks!" (This is bad because it stops the conversation flow).

15. **"ABANDONED CART" DETECTION:** If a user has provided a service, a date, AND a time, but then goes silent or asks a non-confirming question, you MUST set the intent to 'BOOKING_ABANDONED'.

*CONVERSATIONAL TIPS:**

*   **USE HISTORY & AVOID REPETITION:** Pay close attention to the conversation history. Do not repeat information or ask questions that have already been answered. Acknowledge what the user has already told you.
*   **ADD PERSONALITY:** Maintain a friendly, professional, and helpful tone. Use emojis where appropriate (e.g., 😊, 👍) to keep the conversation light, but do not overuse them.
*   **BE SAFE:** Do not make up prices or services. Do not include any external links in your replies.

**CONVERSATIONAL FLOW EXAMPLES:**

*   **Scenario: Broad Inquiry**
    *   User asks: "tell me about your hair coloring"
    *   GOOD reply: "We have a few great options for hair coloring, including full color and highlights. To help me recommend the right one, are you looking for a full new color or something to add dimension?"

*   **Scenario: Specific Price Inquiry**
    *   User asks: "how much is full hair coloring?"
    *   GOOD reply: "Our Hair Coloring - Full service is Rs. 900. Would you like to book an appointment?"

*   **Scenario: Specific Specialist Inquiry**
    *   User asks: "who is your best colorist?"
    *   GOOD reply: "Asif is our specialist for hair coloring and does a fantastic job! Would you like to check for an appointment with him?"

*   **Scenario: Date Resolution**
    *   Context: "Today's date is: Saturday, September 06, 2025"
    *   User asks: "appointment for tomorrow"
    *   JSON 'date' entity MUST be "2025-09-07".
    *   GOOD reply: "Certainly! I can book that for you for Sunday, September 7th. What time would be best?"

*   **Scenario: Upselling**
    *   A user confirms a booking for a "Classic Haircut".
    *   GOOD, NATURAL reply: "Perfect, you're all set for the Classic Haircut! Since you'll be here, would you be interested in adding our popular Head Massage for just Rs. 300? It's a great way to relax."
"""

def _get_business_context(db: Session) -> str:
    """
    Helper function to fetch all business data from the new, correct tables.
    """
    context_parts = []

    profile = crud_profile.get_profile(db)
    if profile:
        context_parts.append(f"## Business Information:")
        if profile.address:
            context_parts.append(f"- Location: {profile.address}")
        if profile.phone_number:
            context_parts.append(f"- Contact Number: {profile.phone_number}")

    # 1. Fetch Q&A from the old knowledge table
    knowledge_items = crud_knowledge.get_knowledge_items(db, limit=200)
    qas = [f"- Q: {item.key}\\n  A: {item.value}" for item in knowledge_items if item.type == 'QA']
    if qas: context_parts.append("## Frequently Asked Questions:\\n" + "\\n".join(qas))
    
    # --- 2. FETCH FROM NEW MENU & UPSELL TABLES ---
    menu_items = crud_menu.get_menu_items(db)
    if menu_items:
        # Format the menu for the AI
        menu_list = [f"- {item.name} ({item.category}): Rs. {item.price}. Description: {item.description}" for item in menu_items]
        context_parts.append("## Menu & Pricing:\\n" + "\\n".join(menu_list))
        
        # Format the upsell rules for the AI
        upsell_rules = [
            f"- TRIGGER: {item.name} -> SUGGESTS: {item.upsell_rule.upsold_service.name} with message: '{item.upsell_rule.suggestion_text}'"
            for item in menu_items if item.upsell_rule and item.upsell_rule.upsold_service
        ]
        if upsell_rules:
            context_parts.append("## Upsell Rules:\\n" + "\\n".join(upsell_rules))
            
    # 3. Fetch Staff Roster (unchanged)
    staff_members = crud_knowledge.get_staff_members(db, limit=50)
    if staff_members:
        staff_list = [f"- {member.name} (Specialties: {member.specialties})" for member in staff_members]
        context_parts.append("## Staff & Specialties:\\n" + "\\n".join(staff_list))

    return "\\n\\n".join(context_parts)

def analyze_message(
    chat_history: List[Dict],
    db: Session,
    db_contact: 'models.Contact',
    is_new_customer: bool,
    is_new_interaction: bool,
    relevant_tags: List[str],
    booking_history_context: str
) -> Dict:
    """
    Generates a reply using the Gemini model, now including BOTH business AND customer context.
    """
    
    try:
        last_user_message = chat_history[-1]['parts'][0] if chat_history else ""
        retrieved_context_str = context_retriever.find_relevant_context(last_user_message, db)
    
        # --- Step 1: Fetch dynamic business context (unchanged) ---
        print("🏢 Fetching business profile from database...")
        profile = crud_profile.get_profile(db)
        business_name = profile.business_name
        business_description = profile.business_description
        
        # --- Step 2: Build the NEW Dynamic Customer Context String ---
        customer_context_string = ""
        if is_new_interaction:
            if is_new_customer:
                customer_context_string = "Customer Status: This is a NEW_CUSTOMER."
            else:
                customer_context_string = f'Customer Status: This is a RETURNING_CUSTOMER named "{db_contact.name}".'
        else:
            customer_context_string = f'Customer Status: This is an ongoing conversation with "{db_contact.name or "the user"}".'

        # --- Step 3: Prepare the full, merged system instruction ---
        print(f"🤖 Building prompt with customer context: '{customer_context_string}'")
        today_str = datetime.now().strftime("%A, %B %d, %Y")

        system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
            business_name=business_name,
            business_description=business_description,
            current_date=today_str,
            customer_context_string=customer_context_string,
            list_of_relevant_tags=str(relevant_tags) if relevant_tags else "[]",
            retrieved_context=retrieved_context_str,
            booking_history_context=booking_history_context
        )

        # --- Step 4: Call the Gemini API (unchanged) ---
        print(f"🤖 Sending conversation history ({len(chat_history)} messages) and context to Gemini...")
        model = genai.GenerativeModel(
            'gemini-2.5-flash-lite', # Recommend 'gemini-pro' for this level of complexity
            system_instruction=system_instruction
        )
        # ... (The rest of your API call and JSON cleaning logic is perfect and remains unchanged) ...
        generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
        response = model.generate_content(chat_history, generation_config=generation_config)
        
        # =========================================================================
        if not response.candidates:
            # This happens if the prompt itself was blocked by safety filters.
            print("❌ Gemini response was blocked. No candidates returned.")
            # We can inspect the reason if needed.
            print(f"   - Prompt Feedback: {response.prompt_feedback}")
            raise ValueError("Blocked by API safety filters (prompt).")
            
        # Also check the finish reason of the first candidate.
        first_candidate = response.candidates[0]
        if first_candidate.finish_reason.name != "STOP":
            print(f"❌ Gemini response finished with non-STOP reason: {first_candidate.finish_reason.name}")
            print(f"   - Safety Ratings: {first_candidate.safety_ratings}")
            raise ValueError(f"Blocked by API safety filters (response: {first_candidate.finish_reason.name}).")
        # =========================================================================


        raw_response_text = response.text
        print(f"✅ Gemini Raw Response: {raw_response_text}")
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response_text, re.DOTALL)
        if not json_match:
            # Fallback for raw JSON without code fences
            json_match = re.search(r'(\{.*?\n\})', raw_response_text, re.DOTALL)
        
        if not json_match:
            print("❌ No valid JSON block found in Gemini's response.")
            raise ValueError("Response does not contain a JSON object.")

        json_string = json_match.group(1) # Group 1 to get the content inside
        print(f"✅ Extracted JSON String: {json_string}")
        
        return json.loads(json_string)
        
    except Exception as e:
        # ... (Your existing robust error handling is perfect) ...
        print(f"❌ An error occurred during Gemini communication or JSON parsing: {e}")
        return {
            "intent": "HUMAN_HANDOFF",
            "entities": {},
            "tags": ["error:ai_parsing_fault"],
            "reply": "That's a good question and I want to make sure you get the right answer. I'm connecting you with our Salon Manager now, and they will be in touch with you here shortly. Thanks for your patience!",
            "confidence_score": 0.0
        }
    
def generate_tagging_rules_from_menu(menu_items: List[models.MenuItem]) -> List[Dict]:
    """
    Uses a specialized Gemini prompt to analyze a list of menu items
    and generate a list of suggested keyword-to-tag rules.
    """
    print("🧠 Calling Gemini for smart tag generation...")
    if not menu_items:
        return []

    # Format the menu for the AI prompt
    menu_list_str = "\n".join([f"- {item.name} (Description: {item.description or 'N/A'})" for item in menu_items])

    generation_prompt = f"""
    You are an expert marketing analyst for a local service business. Your task is to analyze a list of services from a business's menu and generate a list of relevant keywords that customers might use to inquire about them. Your goal is to create tags that are useful for future marketing campaigns.

    **CRITICAL RULES:**
    1.  **Analyze and Group:** Look for patterns. If you see "Haircut - Women's", "Haircut - Men's", and "Haircut - Kids", you must recognize that "haircut" is the base service and "women's", "men's", "kids" are modifiers.
    2.  **Create Specific Tags:** For each unique service, create a specific, hyphenated tag. For example, "Haircut - Women's" should produce a tag like `interest:womens-haircut`. The tag should be lowercase and "slugified" (no spaces or special characters).
    3.  **Identify All Relevant Keywords:** For each specific tag, list ALL the keywords a user might type to find it. "Haircut - Women's" could be found by typing "haircut", "ladies haircut", "women's cut", or "haircut for women".
    4.  **Consolidate Keywords:** If multiple services share a general keyword (like "haircut"), you should link that keyword to the most general or primary service tag.
    5.  **Output Format:** Your response MUST be ONLY a single, valid JSON object with a single key "rules". Do not add any text, code fences, or explanations.
    6.  **JSON Structure:** The JSON must be an array of objects, where each object contains a SINGLE keyword and the ONE specific tag it should apply. If a tag has multiple keywords, create a separate object for each keyword. `[{{"keyword": "...", "suggested_tag_name": "..."}}]`

    **EXAMPLE:**
    *   INPUT MENU:
        - Haircut - Women's (Category: Hair)
        - Haircut - Men's (Category: Hair)
        - Bridal Makeup Package (Category: Makeup)
    *   YOUR JSON OUTPUT:
        {{
            "rules": [
                {{ "keyword": "haircut", "suggested_tag_name": "interest:haircut" }},
                {{ "keyword": "ladies haircut", "suggested_tag_name": "interest:womens-haircut" }},
                {{ "keyword": "womens cut", "suggested_tag_name": "interest:womens-haircut" }},
                {{ "keyword": "mens haircut", "suggested_tag_name": "interest:mens-haircut" }},
                {{ "keyword": "bridal", "suggested_tag_name": "interest:bridal-makeup" }},
                {{ "keyword": "makeup", "suggested_tag_name": "interest:bridal-makeup" }}
            ]
        }}

    ---
    **MENU TO ANALYZE:**
    {menu_list_str}
    """

    try:
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        response = model.generate_content(generation_prompt)
        
        if not response.candidates:
            print("❌ Gemini response was blocked. No candidates returned.")
            if hasattr(response, 'prompt_feedback'):
                print(f"   - Prompt Feedback: {response.prompt_feedback}")
            return []

        # 2. Get the first candidate from the list.
        first_candidate = response.candidates[0]
        
        # 3. NOW, check the finish_reason on the individual candidate object.
        if first_candidate.finish_reason.name != "STOP":
            print(f"❌ Gemini response finished with non-STOP reason: {first_candidate.finish_reason.name}")
            if hasattr(first_candidate, 'safety_ratings'):
                print(f"   - Safety Ratings: {first_candidate.safety_ratings}")
            return []
        # =========================================================================

        raw_response_text = response.text
        if not raw_response_text.strip():
            print("❌ Gemini returned an empty text response.")
            return []
            
        print(f"✅ Gemini Raw Response: {raw_response_text}")

        # JSON Extractor (this part is correct and remains the same)
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response_text, re.DOTALL)
        json_string = ""
        if json_match:
            json_string = json_match.group(1)
        else:
            json_string = raw_response_text

        print(f"✅ Extracted JSON String for parsing: {json_string}")
        
        json_response = json.loads(json_string)
        rules = json_response.get("rules", [])
        
        if not isinstance(rules, list):
            print(f"❌ AI returned JSON, but the 'rules' key is not a list. Type: {type(rules)}")
            return []

        print(f"   - Gemini (Advanced) successfully suggested {len(rules)} new keyword-tag rules.")
        return rules

    except json.JSONDecodeError as e:
        print(f"❌ JSON Parsing Error after extraction. The content inside the JSON is invalid. Error: {e}")
        print(f"   - Attempted to parse: {json_string}")
        return []
    except Exception as e:
        print(f"❌ An unexpected error occurred during advanced AI tag generation: {e}")
        return []