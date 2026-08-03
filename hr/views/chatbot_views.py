"""
Chatbot views — handles AJAX chat messages from the floating widget.
"""
import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from hr.services.chatbot_service import HRChatbotService


@require_POST
def chatbot_reply(request):
    """
    Receives a JSON payload ``{"message": "..."}`` from the chat widget,
    runs it through the rule-based HRChatbotService, stores the last 10
    exchanges in the session, and returns the bot's response.
    """
    try:
        body = json.loads(request.body)
        user_message = (body.get('message') or '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse(
            {'status': 'error', 'response': 'Invalid request format.'},
            status=400,
        )

    if not user_message:
        return JsonResponse(
            {'status': 'error', 'response': 'Please type a message.'},
            status=400,
        )

    # Compute bot response
    service = HRChatbotService(user=request.user if request.user.is_authenticated else None)
    bot_response = service.get_response(user_message)

    # Persist last 10 exchanges in the session
    history = request.session.get('chatbot_history', [])
    history.append({'role': 'user', 'text': user_message})
    history.append({'role': 'bot', 'text': bot_response})
    request.session['chatbot_history'] = history[-20:]  # 10 exchanges = 20 messages

    return JsonResponse({'status': 'success', 'response': bot_response})
